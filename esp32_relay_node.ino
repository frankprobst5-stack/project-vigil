#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <ArduinoJson.h> // Requires installing the ArduinoJson library

// 🌐 NETWORK AND CONTROLLER CONFIGURATION
const char* ssid = "YOUR_LOCAL_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";
const char* server_address = "http://127.0.0"; // Replace with your Ubuntu machine's real local IP!

// 🔌 HARDWARE PROFILE CONFIGURATION
const char* device_id = "ESP32_RELAY_BETA";
const char* device_type = "Physical Smart Switch";
const int RELAY_PIN = 5; // The physical pin wired to your relay switch module
bool relay_state = false;

WebServer server(80); // Open port 80 on the chip to listen for toggle commands from the hub

void registerWithHub() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(server_address);
    http.addHeader("Content-Type", "application/json");

    // Build the exact JSON data package your Python server demands
    JsonDocument doc;
    doc["device_id"] = device_id;
    doc["ip"] = WiFi.localIP().toString();
    doc["type"] = device_type;
    doc["state"] = relay_state ? "ON" : "OFF";

    String requestBody;
    serializeJson(doc, requestBody);

    int httpResponseCode = http.POST(requestBody);
    if (httpResponseCode > 0) {
      Serial.print("✨ [REGISTRATION] Checked in with Project Vigil Core. Code: ");
      Serial.println(httpResponseCode);
    } else {
      Serial.print("⚠️ [REGISTRATION ERROR] Hub connection failed: ");
      Serial.println(http.errorToString(httpResponseCode).c_str());
    }
    http.end();
  }
}

// 🚀 THIS HANDLES INTERACTION WHEN YOU CLICK "TOGGLE RELAY" ON YOUR FIREFOX DASHBOARD
void handleControlRequest() {
  if (server.hasArg("state")) {
    String stateCmd = server.arg("state");
    if (stateCmd == "ON") {
      relay_state = true;
      digitalWrite(RELAY_PIN, HIGH); // Shoot 3.3v of electricity to flip the physical relay on
    } else if (stateCmd == "OFF") {
      relay_state = false;
      digitalWrite(RELAY_PIN, LOW);  // Drop electricity to turn the physical relay off
    }
    Serial.print("🔌 [RELAY STATE CHANGED] Target hardware set to: ");
    Serial.println(stateCmd);
    
    server.send(200, "text/plain", "OK");
    registerWithHub(); // Instantly report the fresh state back to Python to keep UI in sync
  } else {
    server.send(400, "text/plain", "Bad Request");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW); // Start with the switch safely off

  // Connect to the localized off-grid Wi-Fi network
  Serial.print("📡 Connecting to Wi-Fi Network...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✓ Wireless uplink locked!");
  Serial.print("📌 Node Local IP Address: ");
  Serial.println(WiFi.localIP());

  // Setup the server route to listen for incoming toggle directives from Python
  server.on("/control", HTTP_POST, handleControlRequest);
  server.begin();

  // Issue the initial registration broadcast into the airwaves
  registerWithHub();
}

void loop() {
  server.handleClient(); // Constantly listen for web command packets from Python
  
  // Every 30 seconds, send a heartbeat package to let the hub know this node is still online
  static unsigned long lastHeartbeat = 0;
  if (millis() - lastHeartbeat > 30000) {
    lastHeartbeat = millis();
    registerWithHub();
  }
}

