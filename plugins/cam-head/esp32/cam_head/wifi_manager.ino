// Last modified: 2026-06-06-22-28-12
// wifi_manager.ino — multi-network WiFi + NVS persistence
// Compiled as part of the cam_head sketch by Arduino IDE.
// All globals (networks, networkCount, prefs, currentMode, etc.) are in cam_head.ino.
//
// NVS namespaces:
//   "wifi_cfg"  — network list  (count, s0–s4, p0–p4)
//   "cam_cfg"   — device config (mode)

// ─── Mode NVS ────────────────────────────────────────────────────────────────

void loadModeFromFlash() {
    prefs.begin("cam_cfg", true);
    currentMode = prefs.getInt("mode", CAM_HEAD_MODE_DEFAULT);
    prefs.end();
    currentMode = constrain(currentMode, 1, 3);
}

void saveModeToFlash() {
    prefs.begin("cam_cfg", false);
    prefs.putInt("mode", currentMode);
    prefs.end();
    Serial.printf("[nvs] Mode saved: %d\n", currentMode);
}

// ─── Network NVS ─────────────────────────────────────────────────────────────

void loadNetworksFromFlash() {
    prefs.begin("wifi_cfg", true);
    networkCount = min((int)prefs.getInt("count", 0), MAX_WIFI_NETWORKS);
    for (int i = 0; i < networkCount; i++) {
        networks[i].ssid     = prefs.getString(("s" + String(i)).c_str(), "");
        networks[i].password = prefs.getString(("p" + String(i)).c_str(), "");
    }
    prefs.end();
    Serial.printf("[wifi] Loaded %d network(s)\n", networkCount);
}

void saveNetworksToFlash() {
    prefs.begin("wifi_cfg", false);
    prefs.putInt("count", networkCount);
    for (int i = 0; i < networkCount; i++) {
        prefs.putString(("s" + String(i)).c_str(), networks[i].ssid);
        prefs.putString(("p" + String(i)).c_str(), networks[i].password);
    }
    for (int i = networkCount; i < MAX_WIFI_NETWORKS; i++) {
        prefs.remove(("s" + String(i)).c_str());
        prefs.remove(("p" + String(i)).c_str());
    }
    prefs.end();
    Serial.printf("[wifi] Saved %d network(s)\n", networkCount);
}

// ─── List Management ─────────────────────────────────────────────────────────

bool addNetwork(const String& ssid, const String& password) {
    if (networkCount >= MAX_WIFI_NETWORKS || ssid.isEmpty()) return false;
    networks[networkCount++] = {ssid, password};
    return true;
}

bool removeNetwork(int idx) {
    if (idx < 0 || idx >= networkCount) return false;
    for (int i = idx; i < networkCount - 1; i++) networks[i] = networks[i + 1];
    networkCount--;
    return true;
}

bool moveNetworkUp(int idx) {
    if (idx <= 0 || idx >= networkCount) return false;
    WifiNetwork tmp   = networks[idx];
    networks[idx]     = networks[idx - 1];
    networks[idx - 1] = tmp;
    return true;
}

bool moveNetworkDown(int idx) {
    if (idx < 0 || idx >= networkCount - 1) return false;
    WifiNetwork tmp   = networks[idx];
    networks[idx]     = networks[idx + 1];
    networks[idx + 1] = tmp;
    return true;
}

// ─── Connection ──────────────────────────────────────────────────────────────

bool connectToNetwork(int idx) {
    if (idx < 0 || idx >= networkCount) return false;
    Serial.printf("[wifi] Trying [%d] %s\n", idx, networks[idx].ssid.c_str());
    WiFi.begin(networks[idx].ssid.c_str(), networks[idx].password.c_str());
    unsigned long t = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - t > WIFI_TIMEOUT_MS) { WiFi.disconnect(true); return false; }
        delay(200);
    }
    Serial.printf("[wifi] Connected — IP: %s\n", WiFi.localIP().toString().c_str());
    return true;
}

bool connectToAnyNetwork() {
    if (networkCount == 0) return false;
    if (WiFi.status() == WL_CONNECTED) return true;
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(true);
    delay(200);

    Serial.println("[wifi] Scanning...");
    int found = WiFi.scanNetworks(false, true);

    if (found > 0) {
        for (int i = 0; i < networkCount; i++) {
            for (int j = 0; j < found; j++) {
                if (WiFi.SSID(j) == networks[i].ssid) {
                    Serial.printf("[wifi] Visible: %s (%d dBm)\n",
                                  networks[i].ssid.c_str(), WiFi.RSSI(j));
                    WiFi.scanDelete();
                    if (connectToNetwork(i)) return true;
                    break;
                }
            }
        }
        WiFi.scanDelete();
    } else {
        for (int i = 0; i < networkCount; i++) {
            if (connectToNetwork(i)) return true;
        }
    }
    return false;
}

static unsigned long _wifiLostSince = 0;

void maintainWifi() {
    if (millis() - lastWifiCheck < WIFI_CHECK_INTERVAL_MS) return;
    lastWifiCheck = millis();

    if (WiFi.status() == WL_CONNECTED) {
        _wifiLostSince = 0;
        return;
    }

    // Wait for confirmed outage before triggering reconnect.
    // ESP32 WiFi+BLE coexistence can cause transient non-WL_CONNECTED reads.
    if (_wifiLostSince == 0) {
        _wifiLostSince = millis();
        Serial.println("[wifi] Status not connected — will verify next interval");
        return;
    }

    _wifiLostSince = 0;
    Serial.println("[wifi] Lost — reconnecting...");
    if (connectToAnyNetwork()) MDNS.begin(MDNS_HOSTNAME);
}
