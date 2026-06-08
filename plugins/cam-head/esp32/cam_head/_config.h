// Last modified: 2026-06-06-22-28-12
#pragma once

// ─── Device Identity ─────────────────────────────────────────────────────────
// Change these per physical device before flashing.
#define PLUGIN_ID     "cam-head-1"
#define PLUGIN_NAME   "Camera Head 1"
#define MDNS_HOSTNAME "cam-head-1"    // reachable as cam-head-1.local

// ─── Operating Mode ───────────────────────────────────────────────────────────
// Runtime mode is stored in NVS and can be changed via BLE or hub command.
// This value is loaded as the factory default on first boot.
#define CAM_HEAD_MODE_SERVO_ONLY  1
#define CAM_HEAD_MODE_GOPRO_ONLY  2
#define CAM_HEAD_MODE_FULL        3   // servo + GoPro bridge

#define CAM_HEAD_MODE_DEFAULT  CAM_HEAD_MODE_FULL

// ─── Bluetooth ───────────────────────────────────────────────────────────────
// BLE Nordic UART Service — nRF Toolbox / LightBlue / nRF Connect (iOS + Android).
#define BT_DEVICE_NAME  "CamHead-1"

// ─── WiFi (main network) ─────────────────────────────────────────────────────
// Factory-default network loaded on first boot when NVS is empty.
// After first boot, networks are managed via BLE.
#define WIFI_DEFAULT_SSID     "WifiNetworkSSID"
#define WIFI_DEFAULT_PASSWORD "WifiNetworkPassword"
#define WIFI_TIMEOUT_MS       12000
#define MAX_WIFI_NETWORKS     5       // index 0 = highest priority

// ─── GoPro Hero 4 ─────────────────────────────────────────────────────────────
// GoPro creates its own WiFi hotspot. ESP32 switches to it temporarily,
// executes HTTP API calls, then reconnects to the main network.
#define GOPRO_SSID              "GoProWifiSSID"   // GoPro's WiFi name
#define GOPRO_PASSWORD          "GoProWifiPassword"      // GoPro's WiFi password
#define GOPRO_HOST              "10.5.5.9"           // GoPro fixed IP
#define GOPRO_PORT              80
// Static IP for ESP32 on GoPro network — skips DHCP, speeds up connect.
#define GOPRO_STATIC_IP         "10.5.5.100"
#define GOPRO_GATEWAY           "10.5.5.9"
#define GOPRO_SUBNET            "255.255.255.0"
// Timeouts
#define GOPRO_CONNECT_TIMEOUT_MS 5000   // max wait to join GoPro WiFi
#define GOPRO_HTTP_TIMEOUT_MS    3000   // max wait per HTTP request

// ─── Hub Discovery ───────────────────────────────────────────────────────────
#define DISCOVERY_PORT 9999

// ─── Servo GPIO Pins (MG90S) ─────────────────────────────────────────────────
#define PAN_SERVO_PIN  12
#define TILT_SERVO_PIN 13

// ─── MG90S Pulse Limits ──────────────────────────────────────────────────────
#define SERVO_MIN_US  500
#define SERVO_MAX_US  2400

// ─── Pan / Tilt Angle Limits ─────────────────────────────────────────────────
#define PAN_MIN_DEG   0
#define PAN_MAX_DEG   180
#define PAN_CENTER    90

#define TILT_MIN_DEG  0
#define TILT_MAX_DEG  90     // physical stop — adjust per mounting
#define TILT_CENTER   45

// ─── Timing ──────────────────────────────────────────────────────────────────
#define HEARTBEAT_INTERVAL_MS  5000
#define WIFI_CHECK_INTERVAL_MS 15000
