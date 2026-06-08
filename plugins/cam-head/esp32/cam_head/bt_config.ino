// Last modified: 2026-06-06-22-28-12
// bt_config.ino — BLE Nordic UART Service config interface
// Compiled as part of the cam_head sketch by Arduino IDE.
// All globals and BLE includes are in cam_head.ino.
//
// Compatible apps (iOS + Android):
//   nRF Toolbox  — Nordic Semiconductor (UART tab)
//   LightBlue    — PunchThrough Design
//   nRF Connect  — Nordic Semiconductor
//
// Configure app to send CR+LF after each command.

#define NUS_SERVICE_UUID  "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_RX_UUID       "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define NUS_TX_UUID       "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

#define BLE_CMD_MAX  128

static QueueHandle_t _bleQueue    = nullptr;
static char          _rxBuf[BLE_CMD_MAX] = {0};
static int           _rxLen       = 0;
static bool          _showWelcome = true;

// ─── BLE Callbacks ───────────────────────────────────────────────────────────

class BLEServerCB : public BLEServerCallbacks {
    void onConnect(BLEServer*) override {
        bleConnected  = true;
        _showWelcome  = true;
        Serial.println("[ble] Client connected");
    }
    void onDisconnect(BLEServer* srv) override {
        bleConnected  = false;
        btInputState  = BT_IDLE;
        btPendingSsid = "";
        _rxLen        = 0;
        memset(_rxBuf, 0, BLE_CMD_MAX);
        srv->startAdvertising();
        Serial.println("[ble] Client disconnected — advertising resumed");
    }
};

class NUSRxCB : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic* pChar) override {
        String val = pChar->getValue();
        for (char c : val) {
            if (c == '\r') continue;
            if (c == '\n') {
                if (_rxLen > 0 && _bleQueue) {
                    char line[BLE_CMD_MAX] = {0};
                    memcpy(line, _rxBuf, _rxLen);
                    xQueueSend(_bleQueue, line, 0);
                }
                _rxLen = 0;
                memset(_rxBuf, 0, BLE_CMD_MAX);
            } else if (_rxLen < BLE_CMD_MAX - 1) {
                _rxBuf[_rxLen++] = c;
            }
        }
    }
};

// ─── Send Helpers ─────────────────────────────────────────────────────────────

static void bleSend(const char* s, size_t len) {
    if (!bleConnected || !bleTxChar || len == 0) return;
    const size_t CHUNK = 64;
    for (size_t off = 0; off < len; off += CHUNK) {
        size_t n = (len - off < CHUNK) ? len - off : CHUNK;
        bleTxChar->setValue((uint8_t*)(s + off), n);
        bleTxChar->notify();
        if (off + CHUNK < len) vTaskDelay(pdMS_TO_TICKS(15));
    }
}

static void blePrint(const char* s)   { bleSend(s, strlen(s)); }
static void blePrintln(const char* s) { blePrint(s); blePrint("\r\n"); }
static void blePrintln()              { blePrint("\r\n"); }

static void blePrintf(const char* fmt, ...) {
    char buf[192];
    va_list a;
    va_start(a, fmt);
    vsnprintf(buf, sizeof(buf), fmt, a);
    va_end(a);
    blePrint(buf);
}

// ─── Command Handlers ─────────────────────────────────────────────────────────

static void bleHelp() {
    blePrintln("── WiFi ──────────────────────────────");
    blePrintln("  status         WiFi / hub / servo / GoPro");
    blePrintln("  list           saved networks (priority order)");
    blePrintln("  scan           scan visible WiFi networks");
    blePrintln("  add            add network (prompts SSID then password)");
    blePrintln("  remove <n>     remove network at index n");
    blePrintln("  up/down <n>    change priority");
    blePrintln("  connect [n]    (re)connect");
    blePrintln("  save           write changes to flash");
    blePrintln("  clear          delete all saved networks");
    blePrintln("── Device ────────────────────────────");
    blePrintln("  mode [1|2|3]   set mode (1=servo 2=gopro 3=both), reboots");
    blePrintln("  gopro          show last GoPro status");
    blePrintln("  gopro poll     force GoPro status poll now");
    blePrintln("  reboot         restart device");
}

static void bleStatus() {
    const char* modeStr = currentMode == 1 ? "SERVO only"
                        : currentMode == 2 ? "GOPRO only"
                        : "SERVO + GOPRO";
    blePrintf("Mode: %d (%s)\r\n", currentMode, modeStr);
    blePrintln("-- WiFi --");
    if (WiFi.status() == WL_CONNECTED) {
        blePrintf("  SSID : %s\r\n", WiFi.SSID().c_str());
        blePrintf("  IP   : %s\r\n", WiFi.localIP().toString().c_str());
        blePrintf("  RSSI : %d dBm\r\n", WiFi.RSSI());
    } else {
        blePrintln("  Not connected");
    }
    blePrintln("-- Hub --");
    blePrintf("  URL  : %s\r\n", hubUrl.isEmpty() ? "not discovered" : hubUrl.c_str());
    blePrintf("  Conn : %s\r\n", hubConnected ? "yes" : "no");
    if (servoEnabled()) {
        blePrintln("-- Servo --");
        blePrintf("  Pan  : %d deg\r\n", currentPan);
        blePrintf("  Tilt : %d deg\r\n", currentTilt);
    }
    if (goProEnabled()) {
        blePrintln("-- GoPro --");
        if (!goProState.valid) blePrintln("  No data yet");
        else {
            blePrintf("  Rec  : %s\r\n",    goProState.recording ? "yes" : "no");
            blePrintf("  Batt : %d/4\r\n",  goProState.battery);
            blePrintf("  SD   : %s\r\n",    goProState.sd_ok ? "ok" : "missing");
            blePrintf("  Left : %d min\r\n", goProState.remainingSecs / 60);
        }
    }
}

static void bleList() {
    if (networkCount == 0) { blePrintln("No networks saved."); return; }
    String active = (WiFi.status() == WL_CONNECTED) ? WiFi.SSID() : "";
    for (int i = 0; i < networkCount; i++)
        blePrintf("  [%d] %s%s\r\n", i, networks[i].ssid.c_str(),
                  (networks[i].ssid == active) ? " *" : "");
    blePrintln("  (* = currently connected)");
}

static void bleScan() {
    blePrintln("Scanning...");
    int n = WiFi.scanNetworks(false, true);
    if (n <= 0) { blePrintln("Nothing found."); return; }
    for (int i = 0; i < min(n, 20); i++)
        blePrintf("  %2d. %-26s %4d dBm%s\r\n", i + 1,
                  WiFi.SSID(i).c_str(), WiFi.RSSI(i),
                  WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? " open" : "");
    WiFi.scanDelete();
}

static void bleConnect(int idx) {
    bool ok = (idx < 0) ? connectToAnyNetwork() : connectToNetwork(idx);
    if (ok) {
        MDNS.begin(MDNS_HOSTNAME);
        blePrintf("Connected: %s  IP: %s\r\n",
                  WiFi.SSID().c_str(), WiFi.localIP().toString().c_str());
    } else {
        blePrintln("Connection failed.");
    }
}

// ─── Command Parser ───────────────────────────────────────────────────────────

static void processCommand(const char* raw) {
    String line(raw);
    line.trim();
    if (line.isEmpty()) return;

    if (btInputState == BT_AWAIT_SSID) {
        btPendingSsid = line;
        blePrintln("Password:");
        btInputState = BT_AWAIT_PASSWORD;
        return;
    }
    if (btInputState == BT_AWAIT_PASSWORD) {
        if (addNetwork(btPendingSsid, line))
            blePrintf("Added [%d] %s — run 'save'.\r\n", networkCount - 1, btPendingSsid.c_str());
        else
            blePrintf("List full (max %d).\r\n", MAX_WIFI_NETWORKS);
        btInputState  = BT_IDLE;
        btPendingSsid = "";
        return;
    }

    String lower = line;  lower.toLowerCase();
    int    sp    = lower.indexOf(' ');
    String verb  = (sp < 0) ? lower : lower.substring(0, sp);
    String arg   = (sp < 0) ? ""    : line.substring(sp + 1);
    arg.trim();

    if      (verb == "help" || verb == "?") bleHelp();
    else if (verb == "status")  bleStatus();
    else if (verb == "list")    bleList();
    else if (verb == "scan")    bleScan();
    else if (verb == "add")     { btInputState = BT_AWAIT_SSID; blePrintln("SSID:"); }
    else if (verb == "remove")  { removeNetwork(arg.toInt())  ? blePrintln("Removed.") : blePrintln("Invalid."); }
    else if (verb == "up")      { moveNetworkUp(arg.toInt())   ? blePrintln("Moved up.")   : blePrintln("Already top."); }
    else if (verb == "down")    { moveNetworkDown(arg.toInt()) ? blePrintln("Moved down.") : blePrintln("Already bottom."); }
    else if (verb == "connect") bleConnect(arg.isEmpty() ? -1 : arg.toInt());
    else if (verb == "save")    { saveNetworksToFlash(); blePrintln("Saved."); }
    else if (verb == "clear")   { networkCount = 0; blePrintln("Cleared. Run 'save'."); }

    else if (verb == "mode") {
        if (arg.isEmpty()) {
            const char* names[] = {"", "SERVO only", "GOPRO only", "SERVO + GOPRO"};
            blePrintf("Current: %d (%s)\r\nUsage: mode 1|2|3\r\n", currentMode, names[currentMode]);
        } else {
            int m = arg.toInt();
            if (m >= 1 && m <= 3) {
                currentMode = m;
                saveModeToFlash();
                const char* names[] = {"", "SERVO only", "GOPRO only", "SERVO + GOPRO"};
                blePrintf("Mode → %d (%s). Rebooting...\r\n", m, names[m]);
                vTaskDelay(pdMS_TO_TICKS(500));
                ESP.restart();
            } else {
                blePrintln("Usage: mode 1|2|3  (1=servo 2=gopro 3=both)");
            }
        }
    }

    else if (verb == "gopro") {
        String argLow = arg;  argLow.toLowerCase();
        if (argLow == "poll") {
            gopro_requestStatus();
            blePrintln("GoPro status request queued.");
        } else if (!goProEnabled()) {
            blePrintln("GoPro not enabled in current mode.");
        } else if (!goProState.valid) {
            blePrintln("No GoPro data yet.");
        } else {
            blePrintf("  Recording : %s\r\n",    goProState.recording ? "yes" : "no");
            blePrintf("  Battery   : %d/4\r\n",  goProState.battery);
            blePrintf("  Mode      : %d\r\n",    goProState.mode);
            blePrintf("  SD OK     : %s\r\n",    goProState.sd_ok ? "yes" : "no");
            blePrintf("  Remaining : %d min\r\n", goProState.remainingSecs / 60);
        }
    }

    else if (verb == "reboot") {
        blePrintln("Rebooting...");
        vTaskDelay(pdMS_TO_TICKS(500));
        ESP.restart();
    }

    else blePrintf("Unknown: '%s'  Type 'help'.\r\n", verb.c_str());
}

// ─── Main Handler (called from loop()) ───────────────────────────────────────

void handleBtSerial() {
    if (!bleConnected) return;
    if (_showWelcome) {
        vTaskDelay(pdMS_TO_TICKS(200));
        blePrintf("=== %s ===\r\n", PLUGIN_NAME);
        blePrintln("Type 'help' for commands.");
        _showWelcome = false;
    }
    char buf[BLE_CMD_MAX];
    while (_bleQueue && xQueueReceive(_bleQueue, buf, 0) == pdTRUE)
        processCommand(buf);
}

// ─── Init (called from setup()) ───────────────────────────────────────────────

void setupBle() {
    _bleQueue = xQueueCreate(4, BLE_CMD_MAX);

    BLEDevice::init(BT_DEVICE_NAME);
    bleServer = BLEDevice::createServer();
    bleServer->setCallbacks(new BLEServerCB());

    BLEService* svc = bleServer->createService(NUS_SERVICE_UUID);

    bleTxChar = svc->createCharacteristic(NUS_TX_UUID,
        BLECharacteristic::PROPERTY_NOTIFY | BLECharacteristic::PROPERTY_READ);
    bleTxChar->addDescriptor(new BLE2902());

    BLECharacteristic* rxChar = svc->createCharacteristic(NUS_RX_UUID,
        BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
    rxChar->setCallbacks(new NUSRxCB());

    svc->start();

    BLEAdvertising* adv = BLEDevice::getAdvertising();
    adv->addServiceUUID(NUS_SERVICE_UUID);
    adv->setScanResponse(true);
    adv->setMinPreferred(0x06);
    adv->setMaxPreferred(0x12);
    BLEDevice::startAdvertising();

    Serial.printf("[ble] Advertising: %s\n", BT_DEVICE_NAME);
}
