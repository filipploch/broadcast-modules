// Last modified: 2026-06-06-22-28-12
/*
 * cam_head — ESP32 pan/tilt camera head for broadcast-modules
 *
 * Modes (persisted in NVS, changeable via BLE or hub 'set_mode'):
 *   1 = SERVO_ONLY   — MG90S pan/tilt only
 *   2 = GOPRO_ONLY   — GoPro Hero 4 WiFi bridge only
 *   3 = FULL         — both (default)
 *
 * Required libraries (Arduino Library Manager):
 *   arduinoWebSockets  by Markus Sattler
 *   ArduinoJson        by Benoit Blanchon  (v6)
 *   ESP32Servo         by Kevin Harrington
 *
 * Built-in ESP32 libraries (no install needed):
 *   WiFi, ESPmDNS, HTTPClient
 *   BLEDevice/BLEServer/BLEUtils/BLE2902
 *   Preferences
 *
 * Multi-file sketch — Arduino IDE concatenates all .ino files in this order:
 *   cam_head.ino      — globals, setup, loop, hub/servo logic  (this file)
 *   bt_config.ino     — BLE Nordic UART Service config interface
 *   gopro_bridge.ino  — GoPro Hero 4 HTTP bridge + network switching
 *   wifi_manager.ino  — multi-network WiFi + NVS persistence
 */

#include "config.h"
#include <WiFi.h>
#include <ESPmDNS.h>
#include <WebSocketsServer.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <HTTPClient.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <Preferences.h>

// ─── Operating Mode ──────────────────────────────────────────────────────────

int currentMode = CAM_HEAD_MODE_DEFAULT;

inline bool servoEnabled() {
    return currentMode == CAM_HEAD_MODE_SERVO_ONLY || currentMode == CAM_HEAD_MODE_FULL;
}
inline bool goProEnabled() {
    return currentMode == CAM_HEAD_MODE_GOPRO_ONLY || currentMode == CAM_HEAD_MODE_FULL;
}

// ─── WiFi Network Storage ────────────────────────────────────────────────────

struct WifiNetwork {
    String ssid;
    String password;
};

WifiNetwork networks[MAX_WIFI_NETWORKS];
int         networkCount = 0;

// ─── GoPro State (shared with bt_config.ino and gopro_bridge.ino) ────────────

struct GoProStatus {
    bool  recording;
    int   battery;
    int   mode;
    bool  sd_ok;
    int   remainingSecs;
    bool  valid;
};

GoProStatus goProState = {};

// ─── BLE (shared with bt_config.ino) ─────────────────────────────────────────

BLEServer*         bleServer    = nullptr;
BLECharacteristic* bleTxChar    = nullptr;
bool               bleConnected = false;

enum BtInputState { BT_IDLE, BT_AWAIT_SSID, BT_AWAIT_PASSWORD };
BtInputState btInputState  = BT_IDLE;
String       btPendingSsid = "";

// ─── NVS ─────────────────────────────────────────────────────────────────────

Preferences prefs;

// ─── WebSocket / Hub ─────────────────────────────────────────────────────────

WebSocketsServer discoveryServer(DISCOVERY_PORT);
WebSocketsClient hubClient;

String hubUrl  = "";
String hubHost = "";
int    hubPort = 8080;
String hubPath = "/ws";

bool hubConnected  = false;
bool hubRegistered = false;

unsigned long lastHeartbeat = 0;
unsigned long lastWifiCheck = 0;

// ─── Servo ───────────────────────────────────────────────────────────────────

Servo panServo;
Servo tiltServo;

int currentPan  = PAN_CENTER;
int currentTilt = TILT_CENTER;

// ─── URL Parser ──────────────────────────────────────────────────────────────

void parseHubUrl(const String& url, String& host, int& port, String& path) {
    String s = url;
    s.replace("ws://", "");
    int colon = s.indexOf(':');
    int slash  = s.indexOf('/', colon);
    host = s.substring(0, colon);
    port = s.substring(colon + 1, slash).toInt();
    path = s.substring(slash);
}

// ─── Hub Message Senders ─────────────────────────────────────────────────────

void sendHubMessage(JsonDocument& doc) {
    if (!hubConnected) return;
    String out;
    serializeJson(doc, out);
    hubClient.sendTXT(out);
}

void sendRegister() {
    StaticJsonDocument<300> doc;
    doc["from"] = PLUGIN_ID;
    doc["to"]   = "hub";
    doc["type"] = "register";
    JsonObject p = doc.createNestedObject("payload");
    p["id"]             = PLUGIN_ID;
    p["name"]           = PLUGIN_NAME;
    p["component_type"] = "plugin";
    p["type"]           = "cam_head";
    p["version"]        = "1.0.0";
    p["mode"]           = currentMode;
    sendHubMessage(doc);
}

void sendHeartbeat() {
    StaticJsonDocument<128> doc;
    doc["from"] = PLUGIN_ID;
    doc["to"]   = "hub";
    doc["type"] = "heartbeat";
    doc.createNestedObject("payload")["status"] = "alive";
    sendHubMessage(doc);
}

void sendServoStatus() {
    if (!hubConnected || !servoEnabled()) return;
    StaticJsonDocument<256> doc;
    doc["from"] = PLUGIN_ID;
    doc["to"]   = "broadcast:servo_events";
    doc["type"] = "servo_status";
    JsonObject p = doc.createNestedObject("payload");
    p["id"]   = PLUGIN_ID;
    p["pan"]  = currentPan;
    p["tilt"] = currentTilt;
    sendHubMessage(doc);
}

// ─── Servo Control ───────────────────────────────────────────────────────────

void moveTo(int pan, int tilt) {
    if (!servoEnabled()) return;
    pan  = constrain(pan,  PAN_MIN_DEG,  PAN_MAX_DEG);
    tilt = constrain(tilt, TILT_MIN_DEG, TILT_MAX_DEG);
    panServo.write(pan);
    tiltServo.write(tilt);
    currentPan  = pan;
    currentTilt = tilt;
    Serial.printf("[servo] pan=%d tilt=%d\n", pan, tilt);
    sendServoStatus();
}

// ─── Hub Message Handler ─────────────────────────────────────────────────────

void handleHubMessage(uint8_t* payload, size_t length) {
    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, payload, length) != DeserializationError::Ok) return;

    const char* type = doc["type"] | "";

    if (strcmp(type, "registered") == 0) {
        hubRegistered = true;
        Serial.println("[hub] Registered");
        sendServoStatus();
        if (goProEnabled()) gopro_flushPending();

    } else if (strcmp(type, "pan_tilt") == 0) {
        JsonObject p = doc["payload"];
        moveTo(p["pan"] | currentPan, p["tilt"] | currentTilt);

    } else if (strcmp(type, "get_status") == 0) {
        sendServoStatus();

    } else if (strcmp(type, "center") == 0) {
        moveTo(PAN_CENTER, TILT_CENTER);

    } else if (strcmp(type, "gopro_cmd") == 0) {
        if (goProEnabled()) gopro_queueCommand(doc["payload"].as<JsonObject>());

    } else if (strcmp(type, "set_mode") == 0) {
        int m = doc["payload"]["mode"] | 0;
        if (m >= 1 && m <= 3) {
            currentMode = m;
            saveModeToFlash();
            Serial.printf("[mode] Changed to %d — rebooting\n", m);
            delay(200);
            ESP.restart();
        }
    }
}

// ─── WebSocket Event Handlers ─────────────────────────────────────────────────

void onHubEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch (type) {
        case WStype_CONNECTED:
            hubConnected = true;
            Serial.println("[hub] Connected → registering");
            sendRegister();
            break;
        case WStype_DISCONNECTED:
            hubConnected  = false;
            hubRegistered = false;
            Serial.println("[hub] Disconnected");
            break;
        case WStype_TEXT:
            handleHubMessage(payload, length);
            break;
        default:
            break;
    }
}

void onDiscoveryEvent(uint8_t num, WStype_t type, uint8_t* payload, size_t length) {
    if (type != WStype_TEXT) return;

    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, payload, length) != DeserializationError::Ok) return;

    const char* msgType = doc["type"] | "";
    if (strcmp(msgType, "hub_announce") != 0) return;

    const char* newUrl = doc["hub_url"] | "";
    if (strlen(newUrl) == 0) return;

    StaticJsonDocument<128> ack;
    ack["type"]      = "ack";
    ack["status"]    = "discovered";
    ack["plugin_id"] = PLUGIN_ID;
    String ackStr;
    serializeJson(ack, ackStr);
    discoveryServer.sendTXT(num, ackStr);

    String newHubUrl(newUrl);
    if (newHubUrl == hubUrl && hubConnected) {
        Serial.println("[discovery] Already connected to this HUB");
        return;
    }

    Serial.printf("[discovery] HUB: %s\n", newUrl);
    hubUrl = newHubUrl;
    parseHubUrl(hubUrl, hubHost, hubPort, hubPath);

    hubClient.disconnect();
    hubClient.begin(hubHost.c_str(), hubPort, hubPath.c_str());
    hubClient.setReconnectInterval(5000);
}

// ─── Setup ───────────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(115200);
    Serial.printf("\n[boot] %s v1.0.0\n", PLUGIN_NAME);

    loadModeFromFlash();
    Serial.printf("[boot] Mode: %d (%s)\n", currentMode,
        currentMode == 1 ? "SERVO" : currentMode == 2 ? "GOPRO" : "FULL");

    if (servoEnabled()) {
        panServo.setPeriodHertz(50);
        tiltServo.setPeriodHertz(50);
        panServo.attach(PAN_SERVO_PIN,  SERVO_MIN_US, SERVO_MAX_US);
        tiltServo.attach(TILT_SERVO_PIN, SERVO_MIN_US, SERVO_MAX_US);
        panServo.write(PAN_CENTER);
        tiltServo.write(TILT_CENTER);
        Serial.println("[servo] Initialized — centered");
    }

    loadNetworksFromFlash();
    if (networkCount == 0) {
        addNetwork(WIFI_DEFAULT_SSID, WIFI_DEFAULT_PASSWORD);
        saveNetworksToFlash();
        Serial.println("[wifi] Factory default loaded");
    }
    if (connectToAnyNetwork()) {
        if (MDNS.begin(MDNS_HOSTNAME)) Serial.printf("[mdns] %s.local\n", MDNS_HOSTNAME);
    } else {
        Serial.println("[wifi] No network reachable at boot");
    }

    discoveryServer.begin();
    discoveryServer.onEvent(onDiscoveryEvent);
    Serial.printf("[discovery] Listening on :%d\n", DISCOVERY_PORT);

    hubClient.onEvent(onHubEvent);

    if (goProEnabled()) setupGopro();

    setupBle();

    Serial.println("[boot] Ready");
}

// ─── Loop ────────────────────────────────────────────────────────────────────

void loop() {
    discoveryServer.loop();

    if (!hubUrl.isEmpty()) hubClient.loop();

    handleBtSerial();

    if (goProEnabled()) gopro_loop();

    maintainWifi();

    if (hubRegistered && millis() - lastHeartbeat >= HEARTBEAT_INTERVAL_MS) {
        lastHeartbeat = millis();
        sendHeartbeat();
    }
}
