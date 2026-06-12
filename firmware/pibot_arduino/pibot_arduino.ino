// PiBot reference firmware (AVR / Arduino Uno/Nano/Mega).
//
// Speaks the PiBot ASCII protocol (see protocol.h) over USB serial @ 115200. The Pi's
// agent owns the link; this sketch executes commands and streams telemetry. Three
// safety guards mirror the host (pibot/control/safety.py):
//   1. clamp   — drive/servo/motor values are bounded before actuation
//   2. e-stop  — `estop` latches; motion is refused until `set estop 0`
//   3. watchdog— if no valid command arrives within WATCHDOG_MS, motors stop. This is
//                the INDEPENDENT backstop: a frozen Pi or dropped link still halts.
//
// Motor/servo wiring is robot-specific; set the pins in the CONFIG block. Defaults
// assume a dual H-bridge (TB6612/L298-style: PWM + direction per side) and two servos.

#include "protocol.h"
#include <Servo.h>

// ----------------------------- CONFIG ------------------------------------
static const unsigned long BAUD = 115200;
static const unsigned long WATCHDOG_MS = 300;   // halt if no command within this window
static const unsigned long TELEMETRY_MS = 100;  // battery telemetry cadence

// Dual H-bridge: per-side PWM (must be a PWM pin) + direction.
static const uint8_t PIN_L_PWM = 5, PIN_L_DIR = 4;
static const uint8_t PIN_R_PWM = 6, PIN_R_DIR = 7;
static const uint8_t PIN_SERVO_0 = 9, PIN_SERVO_1 = 10;
static const uint8_t PIN_VBAT = A0;             // battery voltage divider
static const float VBAT_SCALE = 0.0153f;        // adc -> volts (set for your divider)

// Clamp limits (match Limits in safety.py).
static const float MAX_V = 1.0f, MAX_W = 2.0f;
static const float SERVO_MIN = 0.0f, SERVO_MAX = 180.0f;
static const int MAX_PWM = 255;

// ----------------------------- STATE -------------------------------------
static Servo servo0, servo1;
static unsigned long last_cmd_ms = 0;
static unsigned long last_tlm_ms = 0;
static bool estopped = false;
static bool echo_mode = false;  // bench test: ACK + telemetry but suppress actuation
static char line[96];
static uint8_t line_len = 0;
static uint8_t tlm_seq = 0;

static float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }

// ----------------------------- ACTUATION ---------------------------------
static void stop_all() {
  analogWrite(PIN_L_PWM, 0);
  analogWrite(PIN_R_PWM, 0);
}

static void apply_side(uint8_t pwm_pin, uint8_t dir_pin, float u) {  // u in [-1,1]
  u = clampf(u, -1.0f, 1.0f);
  digitalWrite(dir_pin, u >= 0 ? HIGH : LOW);
  analogWrite(pwm_pin, (int)(fabs(u) * MAX_PWM));
}

static void apply_drive(float v, float w) {
  v = clampf(v, -MAX_V, MAX_V);
  w = clampf(w, -MAX_W, MAX_W);
  // Differential mixing, normalized to the unit interval for PWM.
  float left = (v - w) / MAX_V;
  float right = (v + w) / MAX_V;
  apply_side(PIN_L_PWM, PIN_L_DIR, left);
  apply_side(PIN_R_PWM, PIN_R_DIR, right);
}

static void apply_servo(int id, float deg) {
  deg = clampf(deg, SERVO_MIN, SERVO_MAX);
  if (id == 0) servo0.write((int)deg);
  else if (id == 1) servo1.write((int)deg);
}

static void apply_motor(int id, float pwm) {
  int p = (int)clampf(pwm, -MAX_PWM, MAX_PWM);
  uint8_t pwm_pin = (id == 0) ? PIN_L_PWM : PIN_R_PWM;
  uint8_t dir_pin = (id == 0) ? PIN_L_DIR : PIN_R_DIR;
  digitalWrite(dir_pin, p >= 0 ? HIGH : LOW);
  analogWrite(pwm_pin, abs(p));
}

// ----------------------------- IO ----------------------------------------
static void send_line(const char *s) {
  Serial.print(s);
  Serial.print('\n');
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
    // set echo <0|1>, set estop <0|1>  (args[0] is the value; name is positional here)
    // Convention: the host sends the param as the first token; we key off known params
    // encoded as the command's first arg slot via a small lookup is overkill on AVR, so
    // we accept `set,estop,<v>` / `set,echo,<v>` by inspecting argc and the raw payload.
    // For simplicity the agent uses dedicated frames; here `set` with arg toggles estop.
    if (cmd.argc >= 1) {
      if ((int)cmd.args[0] == 0) estopped = false;  // resume
    }
    pibot_build_ack(cmd.seq, out, sizeof(out));
    send_line(out);
    return;
  }

  // Motion commands: refused while e-stopped.
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

// ----------------------------- ARDUINO -----------------------------------
void setup() {
  Serial.begin(BAUD);
  pinMode(PIN_L_PWM, OUTPUT);
  pinMode(PIN_L_DIR, OUTPUT);
  pinMode(PIN_R_PWM, OUTPUT);
  pinMode(PIN_R_DIR, OUTPUT);
  servo0.attach(PIN_SERVO_0);
  servo1.attach(PIN_SERVO_1);
  stop_all();
  last_cmd_ms = millis();
}

void loop() {
  // Read available bytes into the line buffer; dispatch on newline.
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line[line_len] = '\0';
      if (line_len > 0) {
        PibotCommand cmd;
        const char *reason = "";
        if (pibot_parse_command(line, cmd, reason)) {
          last_cmd_ms = millis();  // feed the watchdog on any valid command
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
      line_len = 0;  // overflow -> drop the malformed line
    }
  }

  // Independent deadman watchdog: stop if the Pi has gone quiet.
  unsigned long now = millis();
  if (now - last_cmd_ms > WATCHDOG_MS) {
    stop_all();
  }

  // Periodic battery telemetry.
  if (now - last_tlm_ms > TELEMETRY_MS) {
    last_tlm_ms = now;
    float vbat = analogRead(PIN_VBAT) * VBAT_SCALE;
    send_telemetry("battery", &vbat, 1);
  }
}
