// Last modified: 2026-06-06-22-28-12
// gopro_bridge.ino — GoPro Hero 4 HTTP bridge + WiFi network switching
// Compiled as part of the cam_head sketch by Arduino IDE.
// Globals (goProState, lastGoPollMs, hubConnected …) are in cam_head.ino.
// connectToAnyNetwork() defined in wifi_manager.ino.

#include <HTTPClient.h>

// ─── Types ───────────────────────────────────────────────────────────────────

#define GOPRO_CMD_QUEUE_SIZE  4
#define GOPRO_ENDPOINT_MAX    80
#define GOPRO_CMD_TYPE_MAX    32
#define GOPRO_MAX_RESULTS     4

struct GoProCmd {
    char endpoint[GOPRO_ENDPOINT_MAX];
    char cmd_type[GOPRO_CMD_TYPE_MAX];
};

struct GoProResult {
    char cmd_type[GOPRO_CMD_TYPE_MAX];
    bool success;
};

// ─── Statics ─────────────────────────────────────────────────────────────────

static QueueHandle_t _cmdQueue        = nullptr;
static GoProResult   _results[GOPRO_MAX_RESULTS];
static int           _resultCount     = 0;
static bool          _pendingSend     = false;
static bool          _statusRequested = false;

// ─── Network Switching ───────────────────────────────────────────────────────

static bool gopro_connectNetwork() {
    Serial.println("[gopro] Connecting to GoPro WiFi...");
    WiFi.disconnect(true);
    delay(300);

    IPAddress ip, gw, sn;
    ip.fromString(GOPRO_STATIC_IP);
    gw.fromString(GOPRO_GATEWAY);
    sn.fromString(GOPRO_SUBNET);
    WiFi.config(ip, gw, sn);

    WiFi.begin(GOPRO_SSID, GOPRO_PASSWORD);
    unsigned long t = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - t > GOPRO_CONNECT_TIMEOUT_MS) {
            Serial.println("[gopro] Connect timeout");
            WiFi.disconnect(true);
            WiFi.config(INADDR_NONE, INADDR_NONE, INADDR_NONE);
            return false;
        }
        delay(100);
    }
    Serial.printf("[gopro] Connected: %s\n", WiFi.localIP().toString().c_str());
    return true;
}

static void gopro_disconnectNetwork() {
    WiFi.disconnect(true);
    WiFi.config(INADDR_NONE, INADDR_NONE, INADDR_NONE);
    delay(300);
}

// ─── HTTP ────────────────────────────────────────────────────────────────────

static bool gopro_httpGet(const char* path, String& response) {
    HTTPClient http;
    String url = String("http://") + GOPRO_HOST + path;
    http.begin(url);
    http.setTimeout(GOPRO_HTTP_TIMEOUT_MS);
    int code = http.GET();
    bool ok  = (code == HTTP_CODE_OK);
    if (ok) response = http.getString();
    else    Serial.printf("[gopro] GET %s → %d\n", path, code);
    http.end();
    return ok;
}

// ─── Status Parsing ──────────────────────────────────────────────────────────
// Hero 4 status IDs:
//   "2"  battery level   0–4
//   "4"  mode            0=video 1=photo 2=multi
//   "8"  video elapsed   >0 means recording
//   "32" sd_ok           0/1
//   "54" remaining secs

static void gopro_parseStatus(const String& json) {
    StaticJsonDocument<2048> doc;
    if (deserializeJson(doc, json) != DeserializationError::Ok) {
        goProState.valid = false;
        return;
    }
    JsonObject s = doc["status"];
    if (s.isNull()) { goProState.valid = false; return; }

    goProState.battery       = s["2"]  | 0;
    goProState.mode          = s["4"]  | 0;
    goProState.recording     = (s["8"].as<int>() > 0);
    goProState.sd_ok         = (s["32"].as<int>() == 1);
    goProState.remainingSecs = s["54"] | 0;
    goProState.valid         = true;
}

// ─── Hub Senders ─────────────────────────────────────────────────────────────

static void gopro_sendStatusToHub() {
    if (!hubConnected) return;
    StaticJsonDocument<256> doc;
    doc["from"] = PLUGIN_ID;
    doc["to"]   = "broadcast:gopro_events";
    doc["type"] = "gopro_status";
    JsonObject p = doc.createNestedObject("payload");
    p["id"]             = PLUGIN_ID;
    p["recording"]      = goProState.recording;
    p["battery"]        = goProState.battery;
    p["mode"]           = goProState.mode;
    p["sd_ok"]          = goProState.sd_ok;
    p["remaining_secs"] = goProState.remainingSecs;
    p["valid"]          = goProState.valid;
    sendHubMessage(doc);
}

static void gopro_sendResultsToHub() {
    for (int i = 0; i < _resultCount; i++) {
        StaticJsonDocument<192> doc;
        doc["from"] = PLUGIN_ID;
        doc["to"]   = "broadcast:gopro_events";
        doc["type"] = "gopro_result";
        JsonObject p = doc.createNestedObject("payload");
        p["id"]      = PLUGIN_ID;
        p["cmd"]     = _results[i].cmd_type;
        p["success"] = _results[i].success;
        sendHubMessage(doc);
    }
    _resultCount = 0;
}

// ─── Command Queue ────────────────────────────────────────────────────────────

void gopro_queueCommand(JsonObject payload) {
    const char* cmd = payload["cmd"] | "";
    GoProCmd entry  = {};

    if      (strcmp(cmd, "shutter_start") == 0) strncpy(entry.endpoint, "/gp/gpControl/command/shutter?p=1", GOPRO_ENDPOINT_MAX - 1);
    else if (strcmp(cmd, "shutter_stop")  == 0) strncpy(entry.endpoint, "/gp/gpControl/command/shutter?p=0", GOPRO_ENDPOINT_MAX - 1);
    else if (strcmp(cmd, "mode_video")    == 0) strncpy(entry.endpoint, "/gp/gpControl/command/mode?p=0",    GOPRO_ENDPOINT_MAX - 1);
    else if (strcmp(cmd, "mode_photo")    == 0) strncpy(entry.endpoint, "/gp/gpControl/command/mode?p=1",    GOPRO_ENDPOINT_MAX - 1);
    else if (strcmp(cmd, "get_status")    == 0) { _statusRequested = true; return; }
    else {
        const char* raw = payload["endpoint"] | "";
        if (strlen(raw) == 0) return;
        strncpy(entry.endpoint, raw, GOPRO_ENDPOINT_MAX - 1);
    }

    strncpy(entry.cmd_type, cmd, GOPRO_CMD_TYPE_MAX - 1);
    if (_cmdQueue && xQueueSend(_cmdQueue, &entry, 0) != pdTRUE)
        Serial.println("[gopro] Queue full — command dropped");
}

// ─── Public API ───────────────────────────────────────────────────────────────

void gopro_requestStatus() { _statusRequested = true; }

// ─── Deferred Send (called from onHubEvent after registration) ───────────────

void gopro_flushPending() {
    if (!_pendingSend || !hubConnected) return;
    gopro_sendStatusToHub();
    gopro_sendResultsToHub();
    _pendingSend = false;
    Serial.println("[gopro] Deferred results sent");
}

// ─── Main Loop ───────────────────────────────────────────────────────────────

void gopro_loop() {
    if (WiFi.status() != WL_CONNECTED) return;

    bool hasCmd = _cmdQueue && (uxQueueMessagesWaiting(_cmdQueue) > 0);
    if (!hasCmd && !_statusRequested) return;

    _statusRequested = false;

    if (!gopro_connectNetwork()) {
        Serial.println("[gopro] Unreachable — restoring main WiFi");
        connectToAnyNetwork();
        return;
    }

    _resultCount = 0;
    GoProCmd cmd;
    while (_cmdQueue && xQueueReceive(_cmdQueue, &cmd, 0) == pdTRUE) {
        String resp;
        bool ok = gopro_httpGet(cmd.endpoint, resp);
        if (_resultCount < GOPRO_MAX_RESULTS) {
            strncpy(_results[_resultCount].cmd_type, cmd.cmd_type, GOPRO_CMD_TYPE_MAX - 1);
            _results[_resultCount].success = ok;
            _resultCount++;
        }
    }

    String statusJson;
    if (gopro_httpGet("/gp/gpControl/status", statusJson)) gopro_parseStatus(statusJson);
    else                                                    goProState.valid = false;

    gopro_disconnectNetwork();

    if (!connectToAnyNetwork()) {
        Serial.println("[gopro] Failed to rejoin main network");
        return;
    }
    MDNS.begin(MDNS_HOSTNAME);

    // Mark data as pending — will be sent either now (if hub reconnects quickly)
    // or deferred to the next WStype_CONNECTED event via gopro_flushPending().
    _pendingSend = true;
    hubClient.setReconnectInterval(1000);
    unsigned long t = millis();
    while (!hubConnected && millis() - t < 8000) { hubClient.loop(); delay(50); }
    hubClient.setReconnectInterval(5000);

    if (hubConnected) {
        gopro_sendStatusToHub();
        gopro_sendResultsToHub();
        _pendingSend = false;
    } else {
        Serial.println("[gopro] Hub not yet connected — will send on reconnect");
    }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

void setupGopro() {
    _cmdQueue = xQueueCreate(GOPRO_CMD_QUEUE_SIZE, sizeof(GoProCmd));
    Serial.printf("[gopro] Bridge ready  host=%s  (on-demand only)\n", GOPRO_HOST);
}
