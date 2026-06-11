// PiBot ESP32 controller firmware — WIRELESS-FIRST (the primary PiBot controller).
//
// One board does it all: the ESP32 joins Wi-Fi, serves the PiBot protocol over TCP
// :3333, AND drives the motors/servos directly. The Pi connects with
// TcpTransport(esp32_ip, 3333) over Wi-Fi / the ZeroTier overlay — no USB, no Arduino.
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
// PWM/servo use the ESP32 LEDC peripheral (Arduino-ESP32 core 3.x API). Set pins and
// your battery divider in the CONFIG block.

#include "protocol.h"
#include <WiFi.h>

// ----------------------------- CONFIG ------------------------------------
static const char *WIFI_SSID = "your-ssid";
static const char *WIFI_PASS = "your-password";
static const uint16_t TCP_PORT = 3333;

static const unsigned long WATCHDOG_MS = 300;
static const unsigned long TELEMETRY_MS = 100;

// Dual H-bridge (TB6612/L298-style): per-side PWM pin + direction pin.
static const uint8_t PIN_L_PWM = 25, PIN_L_DIR = 26;
static const uint8_t PIN_R_PWM = 32, PIN_R_DIR = 33;
static const uint8_t PIN_SERVO_0 = 18, PIN_SERVO_1 = 19;
static const uint8_t PIN_VBAT = 34;          // ADC1_CH6
static const float VBAT_SCALE = 0.0017f;     // adc(0..4095) -> volts; set for your divider

static const float MAX_V = 1.0f, MAX_W = 2.0f;
static const float SERVO_MIN = 0.0f, SERVO_MAX = 180.0f;
static const int MAX_PWM = 255;

// LEDC parameters.
static const uint32_t MOTOR_FREQ = 20000;    // 20 kHz (inaudible)
static const uint8_t MOTOR_RES = 8;          // 0..255
static const uint32_t SERVO_FREQ = 50;       // 50 Hz
static const uint8_t SERVO_RES = 16;         // 0..65535

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

static uint32_t servo_duty(float deg) {
  deg = clampf(deg, SERVO_MIN, SERVO_MAX);
  // 1 ms (0°) .. 2 ms (180°) pulse within a 20 ms period at 16-bit resolution.
  const float lo = 65536.0f * 1.0f / 20.0f;
  const float hi = 65536.0f * 2.0f / 20.0f;
  return (uint32_t)(lo + (hi - lo) * (deg / 180.0f));
}

static void apply_servo(int id, float deg) {
  if (id == 0) ledcWrite(PIN_SERVO_0, servo_duty(deg));
  else if (id == 1) ledcWrite(PIN_SERVO_1, servo_duty(deg));
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
  ledcAttach(PIN_SERVO_0, SERVO_FREQ, SERVO_RES);
  ledcAttach(PIN_SERVO_1, SERVO_FREQ, SERVO_RES);
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
  server.begin();
  last_cmd_ms = millis();
}

void loop() {
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
