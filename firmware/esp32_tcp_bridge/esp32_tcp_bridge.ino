// PiBot ESP32 Wi-Fi ↔ serial bridge.
//
// Makes the wired AVR motor controller (running firmware/pibot_arduino) reachable over
// Wi-Fi: the ESP32 joins your network, listens on TCP :3333, and transparently forwards
// bytes between the TCP client (the Pi's TcpTransport) and Serial2 (wired to the AVR).
// The PiBot protocol is byte-transparent, so the ESP32 needs no protocol knowledge.
//
// Wiring: ESP32 Serial2 RX(GPIO16) <- AVR TX, ESP32 Serial2 TX(GPIO17) -> AVR RX, GND
// common. (AVR is 5 V, ESP32 is 3.3 V — use a level shifter on the AVR->ESP32 line.)
//
// Alternatively the ESP32 can run the full firmware/pibot_arduino sketch and drive
// motors directly; this bridge is the minimal, lowest-risk wireless option.

#include <WiFi.h>

static const char *WIFI_SSID = "your-ssid";
static const char *WIFI_PASS = "your-password";
static const uint16_t TCP_PORT = 3333;
static const unsigned long LINK_BAUD = 115200;

WiFiServer server(TCP_PORT);
WiFiClient client;

void setup() {
  Serial.begin(115200);                              // debug console
  Serial2.begin(LINK_BAUD, SERIAL_8N1, 16, 17);      // link to the AVR
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
  }
  Serial.print("pibot bridge ready at ");
  Serial.print(WiFi.localIP());
  Serial.print(':');
  Serial.println(TCP_PORT);
  server.begin();
}

void loop() {
  if (!client || !client.connected()) {
    client = server.available();
  }
  if (client && client.connected()) {
    while (client.available() > 0) {
      Serial2.write((uint8_t)client.read());
    }
    while (Serial2.available() > 0) {
      client.write((uint8_t)Serial2.read());
    }
  }
}
