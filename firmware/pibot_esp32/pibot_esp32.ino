// PiBot ESP32 controller firmware — WIRELESS-FIRST (the primary PiBot controller).
//
// One board does it all: the ESP32 joins Wi-Fi, serves the PiBot protocol over TCP
// :3333, AND drives the motors/servos directly. The Pi connects with
// TcpTransport(esp32_ip, 3333) over Wi-Fi (or the Nebula overlay) — no USB, no Arduino.
//
// Speaks the same protocol as the host codec (protocol.h, identical to
// pibot/protocol/codec.py). Three safety guards mirror pibot/control/safety.py, plus a
// wireless-specific one:
//   1. clamp    — drive/servo/motor bounded before actuation
//   2. e-stop   — `estop` latches; motion refused until `set,estop,0`
//   3. watchdog — no valid command within WATCHDOG_MS -> motors stop
//   4. LINK-LOSS— TCP client disconnects -> motors stop immediately (a dropped Wi-Fi
//                 link must not leave the robot driving)
//
// Servos driven via PCA9685 16-channel PWM shield on I2C (SDA=GPIO21, SCL=GPIO22).
// Set pins and your battery divider in the CONFIG block.

#include "protocol.h"
#include <Wire.h>
#include <WiFi.h>
#include <ArduinoOTA.h>  // over-the-air firmware updates (wireless flashing)

// Wi-Fi credentials live in a gitignored secrets.h (copy secrets.h.example). Falling
// back to placeholders keeps the sketch compiling in CI / without secrets.
#if __has_include("secrets.h")
#include "secrets.h"
#endif
#ifndef PIBOT_WIFI_SSID
#define PIBOT_WIFI_SSID "your-ssid"
#endif
#ifndef PIBOT_WIFI_PASS
#define PIBOT_WIFI_PASS "your-password"
#endif
// OTA: empty password = open on the LAN (simplest); set PIBOT_OTA_PASS in secrets.h to
// require a password for wireless flashing. The mDNS hostname is the OTA target.
#ifndef PIBOT_OTA_PASS
#define PIBOT_OTA_PASS ""
#endif
#ifndef PIBOT_OTA_HOST
#define PIBOT_OTA_HOST "pibot-esp32"
#endif

// ----------------------------- CONFIG ------------------------------------
static const char *WIFI_SSID = PIBOT_WIFI_SSID;
static const char *WIFI_PASS = PIBOT_WIFI_PASS;
static const uint16_t TCP_PORT = 3333;

static const unsigned long WATCHDOG_MS = 300;
static const unsigned long TELEMETRY_MS = 100;

// Dual H-bridge (TB6612/L298-style): per-side PWM pin + direction pin.
static const uint8_t PIN_L_PWM = 25, PIN_L_DIR = 26;
static const uint8_t PIN_R_PWM = 32, PIN_R_DIR = 33;
static const uint8_t PIN_VBAT = 34;          // ADC1_CH6
static const float VBAT_SCALE = 0.0017f;     // adc(0..4095) -> volts; set for your divider

static const float MAX_V = 1.0f, MAX_W = 2.0f;
static const float SERVO_MIN = 0.0f, SERVO_MAX = 180.0f;
static const int MAX_PWM = 255;

// LEDC parameters for motors only.
static const uint32_t MOTOR_FREQ = 20000;    // 20 kHz (inaudible)
static const uint8_t MOTOR_RES = 8;          // 0..255

// ----------------------------- PCA9685 ----------------------------------
// 16-channel 12-bit PWM controller. I2C addr 0x40, SDA=GPIO21, SCL=GPIO22.
// Logic powered from ESP32 3V3. Servo rail (V+) needs its own supply.
#define PCA9685_ADDR     0x40
#define PCA9685_MODE1    0x00
#define PCA9685_PRESCALE 0xFE
#define PCA9685_LED0     0x06  // LED0_ON_L; each channel occupies 4 bytes

static void pca_write(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(PCA9685_ADDR);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

static void pca_init() {
  // I2C bus recovery: 9 SCL pulses to release any slave holding SDA low,
  // then a manual STOP condition, before handing control to Wire.
  pinMode(22, OUTPUT); pinMode(21, INPUT_PULLUP);
  for (int i = 0; i < 9; i++) {
    digitalWrite(22, HIGH); delayMicroseconds(10);
    digitalWrite(22, LOW);  delayMicroseconds(10);
  }
  // STOP: SDA low -> SCL high -> SDA high
  pinMode(21, OUTPUT);
  digitalWrite(21, LOW);  delayMicroseconds(10);
  digitalWrite(22, HIGH); delayMicroseconds(10);
  digitalWrite(21, HIGH); delayMicroseconds(10);

  Wire.begin(21, 22);
  delay(20);

  // Full bus scan so we know exactly what is visible
  Serial.println("I2C scan:");
  bool found = false;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("  device at 0x"); Serial.println(addr, HEX);
      found = true;
    }
  }
  if (!found) Serial.println("  no devices found -- check SDA/SCL wiring");

  pca_write(PCA9685_MODE1, 0x00);   // wake, clear sleep
  delay(5);
  pca_write(PCA9685_MODE1, 0x10);   // sleep to allow prescale write
  // prescale = round(25e6 / (4096 * 50)) - 1 = 121  ->  50 Hz servo PWM
  pca_write(PCA9685_PRESCALE, 121);
  pca_write(PCA9685_MODE1, 0x00);   // wake
  delay(5);
  pca_write(PCA9685_MODE1, 0xA0);   // restart + auto-increment
}

static void pca_set_pwm(uint8_t ch, uint16_t on, uint16_t off) {
  Wire.beginTransmission(PCA9685_ADDR);
  Wire.write(PCA9685_LED0 + 4 * ch);
  Wire.write(on  & 0xFF);
  Wire.write(on  >> 8);
  Wire.write(off & 0xFF);
  Wire.write(off >> 8);
  Wire.endTransmission();
}

// ----------------------------- STATE -------------------------------------
WiFiServer server(TCP_PORT);
WiFiClient client;
static unsigned long last_cmd_ms = 0;
static unsigned long last_tlm_ms = 0;
static bool estopped = false;
static bool echo_mode = false;
static char line[96];
static uint8_t line_len = 0;
static uint8_t tlm_seq = 0;

static float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }

// ----------------------------- ACTUATION ---------------------------------
static void stop_all() {
  ledcWrite(PIN_L_PWM, 0);
  ledcWrite(PIN_R_PWM, 0);
}

static void apply_side(uint8_t pwm_pin, uint8_t dir_pin, float u) {  // u in [-1,1]
  u = clampf(u, -1.0f, 1.0f);
  digitalWrite(dir_pin, u >= 0 ? HIGH : LOW);
  ledcWrite(pwm_pin, (uint32_t)(fabs(u) * MAX_PWM));
}

static void apply_drive(float v, float w) {
  v = clampf(v, -MAX_V, MAX_V);
  w = clampf(w, -MAX_W, MAX_W);
  apply_side(PIN_L_PWM, PIN_L_DIR, (v - w) / MAX_V);
  apply_side(PIN_R_PWM, PIN_R_DIR, (v + w) / MAX_V);
}

static void apply_servo(int id, float deg) {
  if (id < 0 || id > 15) return;
  deg = clampf(deg, SERVO_MIN, SERVO_MAX);
  // 50 Hz = 20 ms period; 12-bit = 4096 ticks.
  // 1 ms (0 deg) = ~205 ticks; 2 ms (180 deg) = ~410 ticks.
  uint16_t ticks = (uint16_t)(205.0f + 205.0f * (deg / 180.0f));
  pca_set_pwm((uint8_t)id, 0, ticks);
}

static void apply_motor(int id, float pwm) {
  int p = (int)clampf(pwm, -MAX_PWM, MAX_PWM);
  uint8_t pwm_pin = (id == 0) ? PIN_L_PWM : PIN_R_PWM;
  uint8_t dir_pin = (id == 0) ? PIN_L_DIR : PIN_R_DIR;
  digitalWrite(dir_pin, p >= 0 ? HIGH : LOW);
  ledcWrite(pwm_pin, abs(p));
}

// ----------------------------- IO ----------------------------------------
static void send_line(const char *s) {
  if (client && client.connected()) {
    client.print(s);
    client.print('\n');
  }
}

static void send_telemetry(const char *type, const float *fields, uint8_t n) {
  char out[96];
  pibot_build_telemetry(tlm_seq++, type, fields, n, out, sizeof(out));
  send_line(out);
}

static bool is_motion(const char *name) {
  return strcmp(name, "drive") == 0 || strcmp(name, "servo") == 0 || strcmp(name, "motor") == 0;
}

static void dispatch(const PibotCommand &cmd) {
  char out[48];
  if (strcmp(cmd.name, "estop") == 0) {
    estopped = true;
    stop_all();
    pibot_build_ack(cmd.seq, out, sizeof(out));
    send_line(out);
    return;
  }
  if (strcmp(cmd.name, "stop") == 0) {
    stop_all();
    pibot_build_ack(cmd.seq, out, sizeof(out));
    send_line(out);
    return;
  }
  if (strcmp(cmd.name, "ping") == 0) {
    pibot_build_ack(cmd.seq, out, sizeof(out));
    send_line(out);
    float vbat = analogRead(PIN_VBAT) * VBAT_SCALE;
    send_telemetry("battery", &vbat, 1);
    return;
  }
  if (strcmp(cmd.name, "set") == 0) {
    if (cmd.argc >= 1 && (int)cmd.args[0] == 0) estopped = false;  // resume
    pibot_build_ack(cmd.seq, out, sizeof(out));
    send_line(out);
    return;
  }
  if (is_motion(cmd.name)) {
    if (estopped) {
      pibot_build_nak(cmd.seq, "estop", out, sizeof(out));
      send_line(out);
      return;
    }
    if (!echo_mode) {
      if (strcmp(cmd.name, "drive") == 0 && cmd.argc >= 2) apply_drive(cmd.args[0], cmd.args[1]);
      else if (strcmp(cmd.name, "servo") == 0 && cmd.argc >= 2) apply_servo((int)cmd.args[0], cmd.args[1]);
      else if (strcmp(cmd.name, "motor") == 0 && cmd.argc >= 2) apply_motor((int)cmd.args[0], cmd.args[1]);
    }
    pibot_build_ack(cmd.seq, out, sizeof(out));
    send_line(out);
    return;
  }
  pibot_build_nak(cmd.seq, "unknown", out, sizeof(out));
  send_line(out);
}

static void handle_byte(char c) {
  if (c == '\r') return;
  if (c == '\n') {
    line[line_len] = '\0';
    if (line_len > 0) {
      PibotCommand cmd;
      const char *reason = "";
      if (pibot_parse_command(line, cmd, reason)) {
        last_cmd_ms = millis();
        dispatch(cmd);
      } else {
        char out[48];
        pibot_build_nak(0, reason, out, sizeof(out));
        send_line(out);
      }
    }
    line_len = 0;
  } else if (line_len < sizeof(line) - 1) {
    line[line_len++] = c;
  } else {
    line_len = 0;  // overflow -> drop
  }
}

// ----------------------------- ARDUINO -----------------------------------
void setup() {
  Serial.begin(115200);
  pinMode(PIN_L_DIR, OUTPUT);
  pinMode(PIN_R_DIR, OUTPUT);
  ledcAttach(PIN_L_PWM, MOTOR_FREQ, MOTOR_RES);
  ledcAttach(PIN_R_PWM, MOTOR_FREQ, MOTOR_RES);
  pca_init();
  stop_all();

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(200);
  }
  Serial.print("pibot esp32 controller at ");
  Serial.print(WiFi.localIP());
  Serial.print(':');
  Serial.println(TCP_PORT);

  // Over-the-air updates (wireless flashing). Halt the motors before an update
  // writes flash, so the robot never drives while it is being reflashed.
  ArduinoOTA.setHostname(PIBOT_OTA_HOST);
  if (strlen(PIBOT_OTA_PASS) > 0) {
    ArduinoOTA.setPassword(PIBOT_OTA_PASS);
  }
  ArduinoOTA.onStart([]() { stop_all(); });
  ArduinoOTA.begin();
  Serial.print("OTA ready: ");
  Serial.print(PIBOT_OTA_HOST);
  Serial.println(".local");

  server.begin();
  last_cmd_ms = millis();
}

void loop() {
  ArduinoOTA.handle();  // service wireless-flash requests

  // Accept / maintain a single client.
  if (!client || !client.connected()) {
    WiFiClient incoming = server.available();
    if (incoming) {
      client = incoming;
      last_cmd_ms = millis();
    } else {
      stop_all();  // LINK-LOSS fail-safe: no client -> no motion
    }
  }

  if (client && client.connected()) {
    while (client.available() > 0) {
      handle_byte((char)client.read());
    }
  }

  unsigned long now = millis();
  if (now - last_cmd_ms > WATCHDOG_MS) {
    stop_all();  // deadman watchdog backstop
  }
  if ((now - last_tlm_ms > TELEMETRY_MS) && client && client.connected()) {
    last_tlm_ms = now;
    float vbat = analogRead(PIN_VBAT) * VBAT_SCALE;
    send_telemetry("battery", &vbat, 1);
  }
}
