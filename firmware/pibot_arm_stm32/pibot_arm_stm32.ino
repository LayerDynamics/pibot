// PiBot robot-arm joint controller — Creality 4.2.2 (STM32F103RE). CUSTOM PiBot firmware, NOT Marlin.
//
// Drives up to 4 stepper joints (3 homed; the E0 channel has no endstop input) via step/dir + a
// shared ENABLE, homes each against its endstop, enforces soft limits, and speaks the PiBot CRC
// protocol (protocol.h, identical to pibot/protocol/codec.py) over the board's host UART. This is a
// deliberately DUMB joint-level controller — all arm kinematics/coordination/IK live on the host
// (see docs/plans/2026-06-13-pibot-arm-control.md). One board = one set of joints; the host fans
// commands across the two 4.2.2 boards.
//
// Safety (mirrors the rest of PiBot, SPEC-1 §4):
//   1. clamp     — every jpos target is clamped to the joint's [min_deg, max_deg]; jvel stops at a
//                  soft limit once homed.
//   2. e-stop    — `estop` latches: all motion halts and is refused until `set,estop,0`.
//   3. watchdog  — no valid command within WATCHDOG_MS → motion stops, but steppers stay ENERGIZED
//                  (HOLD) so the arm resists gravity instead of dropping.
//   4. homing    — absolute moves (jpos) are refused until the joint has homed against its endstop.
//
// Commands (CRC frames `>SEQ,NAME,ARG..*CC`):
//   jpos,<id>,<deg>   move joint id to an absolute angle (deg, joint frame)
//   jvel,<id>,<dps>   jog joint id at a velocity (deg/sec); 0 = stop
//   jstop,<id>        stop joint id, hold position
//   home,<id>         home joint id against its endstop
//   estop             latch e-stop · set,<_>,0  clear e-stop · enable,<0|1>  energize/release
//   ping              ack + a telemetry frame
// Telemetry: `<SEQ,joints,d0,d1,..*CC` (joint angles, deg) at TELEMETRY_MS.

#include "protocol.h"
#include <AccelStepper.h>
#include <math.h>

// ---- Host link ---------------------------------------------------------------------------------
// The 4.2.2 has no native USB; its onboard USB-serial chip is wired to USART1 (PA9 TX / PA10 RX).
HardwareSerial HostSerial(PA10, PA9);
#define HOST HostSerial
static const uint32_t BAUD = 115200;

// ---- Shared stepper ENABLE (active-LOW on A4988/TMC2208/2225): PC3 -----------------------------
static const uint8_t PIN_ENABLE = PC3;

// ---- Per-joint config. One entry per joint wired to THIS board (max 4; keep homed joints on the
//      X/Y/Z channels — endstops PA5/PA6/PA7). TUNE the marked values to your real arm. ----------
struct JointCfg {
  uint8_t step_pin, dir_pin, home_pin;
  bool    invert;        // reverse motor vs. joint-angle direction
  bool    home_active_low; // endstop reads LOW when pressed (INPUT_PULLUP + switch to GND)
  int8_t  home_dir;      // joint-angle direction to seek the endstop (+1 / -1)
  float   steps_per_deg; // (motor steps/rev * microstep * gear_ratio) / 360   ⬜ TUNE per joint
  float   min_deg, max_deg; // soft limits                                     ⬜ TUNE per joint
  float   home_pos_deg;  // the joint angle AT the endstop (homed reference)   ⬜ TUNE per joint
  float   max_sps;       // max step rate (steps/sec)                          ⬜ TUNE per joint
  float   accel;         // acceleration (steps/sec^2)                         ⬜ TUNE per joint
  float   home_sps;      // homing seek speed (steps/sec)                      ⬜ TUNE per joint
};

// EXAMPLE: 3 joints (X/Y/Z) on board #1. steps_per_deg example: NEMA17 200 full-steps/rev * 16
// microstep = 3200 steps/rev; 1:1 gear → 3200/360 ≈ 8.889 steps/deg. Multiply by your gear ratio.
static const JointCfg JCFG[] = {
  // step  dir   home  inv   hlow  hdir  s/deg     min     max   homepos  maxsps  accel   homesps
  { PC2,  PB9,  PA5,  false, true,  -1,  8.889f,  -90.f,  90.f,  -90.f,  2000.f, 8000.f,  600.f }, // J0 (X)
  { PB8,  PB7,  PA6,  false, true,  -1,  8.889f,  -90.f,  90.f,  -90.f,  2000.f, 8000.f,  600.f }, // J1 (Y)
  { PB6,  PB5,  PA7,  false, true,  -1,  8.889f,  -90.f,  90.f,  -90.f,  2000.f, 8000.f,  600.f }, // J2 (Z)
};
static const uint8_t NJ = sizeof(JCFG) / sizeof(JCFG[0]);

static const unsigned long WATCHDOG_MS = 300;
static const unsigned long TELEMETRY_MS = 100;
static const float HOME_BACKOFF_DEG = 5.0f;  // back off this far from the endstop after triggering

// ---- Runtime state -----------------------------------------------------------------------------
enum JMode : uint8_t { MODE_IDLE, MODE_POSITION, MODE_VELOCITY, MODE_HOME_SEEK, MODE_HOME_BACKOFF };
static AccelStepper steppers[NJ];
static JMode  jmode[NJ];
static bool   jhomed[NJ];

static bool estopped = false;
static bool enabled = true;
static unsigned long last_cmd_ms = 0;
static unsigned long last_tlm_ms = 0;
static uint8_t tlm_seq = 0;
static char line[96];
static uint8_t line_len = 0;

// ---- Units: joint degrees <-> motor steps (invert folded in here, once) ------------------------
static long deg_to_steps(uint8_t j, float deg) {
  return (long)lroundf(deg * JCFG[j].steps_per_deg) * (JCFG[j].invert ? -1L : 1L);
}
static float steps_to_deg(uint8_t j, long steps) {
  return ((float)steps * (JCFG[j].invert ? -1.f : 1.f)) / JCFG[j].steps_per_deg;
}
static float joint_deg(uint8_t j) { return steps_to_deg(j, steppers[j].currentPosition()); }
static bool endstop_hit(uint8_t j) {
  int v = digitalRead(JCFG[j].home_pin);
  return JCFG[j].home_active_low ? (v == LOW) : (v == HIGH);
}

static float clampf(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }

// ---- Actuation ---------------------------------------------------------------------------------
static void drivers_enable(bool on) {
  digitalWrite(PIN_ENABLE, on ? LOW : HIGH);  // active-LOW
  enabled = on;
}

// Stop all motion. HOLD policy: steppers stay enabled so the arm resists gravity.
static void stop_all() {
  for (uint8_t j = 0; j < NJ; j++) {
    steppers[j].setSpeed(0);
    steppers[j].moveTo(steppers[j].currentPosition());
    jmode[j] = MODE_IDLE;
  }
}

static bool any_active() {
  for (uint8_t j = 0; j < NJ; j++) if (jmode[j] != MODE_IDLE) return true;
  return false;
}

// Begin homing joint j: drive toward the endstop at home_sps.
static void start_home(uint8_t j) {
  if (j >= NJ) return;
  jhomed[j] = false;
  jmode[j] = MODE_HOME_SEEK;
  float sps = JCFG[j].home_sps * (JCFG[j].home_dir >= 0 ? 1.f : -1.f) * (JCFG[j].invert ? -1.f : 1.f);
  steppers[j].setMaxSpeed(JCFG[j].max_sps);
  steppers[j].setSpeed(sps);
}

// Move joint j to an absolute angle. dps > 0 caps this move's speed (deg/sec, clamped to the
// joint's max_sps) — the host uses it to time-scale a coordinated multi-joint move so every joint
// arrives together; dps <= 0 uses the configured max speed.
static void cmd_jpos(uint8_t j, float deg, float dps) {
  if (j >= NJ || !jhomed[j]) return;  // refuse absolute moves before homing
  deg = clampf(deg, JCFG[j].min_deg, JCFG[j].max_deg);
  float sps = JCFG[j].max_sps;
  if (dps > 0.f) {
    float req = dps * JCFG[j].steps_per_deg;
    if (req < sps) sps = req;
  }
  steppers[j].setMaxSpeed(sps);
  steppers[j].moveTo(deg_to_steps(j, deg));
  jmode[j] = MODE_POSITION;
}

static void cmd_jvel(uint8_t j, float dps) {
  if (j >= NJ) return;
  float sps = clampf(dps * JCFG[j].steps_per_deg * (JCFG[j].invert ? -1.f : 1.f),
                     -JCFG[j].max_sps, JCFG[j].max_sps);
  if (sps == 0.f) { steppers[j].setSpeed(0); jmode[j] = MODE_IDLE; return; }
  steppers[j].setSpeed(sps);
  jmode[j] = MODE_VELOCITY;
}

// ---- Per-joint stepping (called every loop) ----------------------------------------------------
static void run_joint(uint8_t j) {
  switch (jmode[j]) {
    case MODE_POSITION:
      steppers[j].run();
      if (steppers[j].distanceToGo() == 0) jmode[j] = MODE_IDLE;
      break;
    case MODE_VELOCITY: {
      // Once homed, refuse to jog past a soft limit (stop at the boundary).
      if (jhomed[j]) {
        float d = joint_deg(j);
        float v = steppers[j].speed();
        bool toward_max = (v > 0) != JCFG[j].invert;  // step-dir → joint-deg direction
        if ((toward_max && d >= JCFG[j].max_deg) || (!toward_max && d <= JCFG[j].min_deg)) {
          steppers[j].setSpeed(0);
          jmode[j] = MODE_IDLE;
          break;
        }
      }
      steppers[j].runSpeed();
      break;
    }
    case MODE_HOME_SEEK:
      if (endstop_hit(j)) {
        steppers[j].setCurrentPosition(deg_to_steps(j, JCFG[j].home_pos_deg));
        float backoff = JCFG[j].home_pos_deg - JCFG[j].home_dir * HOME_BACKOFF_DEG;
        steppers[j].setMaxSpeed(JCFG[j].max_sps);
        steppers[j].moveTo(deg_to_steps(j, backoff));
        jmode[j] = MODE_HOME_BACKOFF;
      } else {
        steppers[j].runSpeed();
      }
      break;
    case MODE_HOME_BACKOFF:
      steppers[j].run();
      if (steppers[j].distanceToGo() == 0) { jhomed[j] = true; jmode[j] = MODE_IDLE; }
      break;
    case MODE_IDLE:
    default:
      break;  // held (steppers energized, not moving)
  }
}

// ---- IO ----------------------------------------------------------------------------------------
static void send_line(const char *s) { HOST.print(s); HOST.print('\n'); }

static void send_state() {
  float deg[NJ];
  for (uint8_t j = 0; j < NJ; j++) deg[j] = joint_deg(j);
  char out[96];
  pibot_build_telemetry(tlm_seq++, "joints", deg, NJ, out, sizeof(out));
  send_line(out);
}

static bool is_motion(const char *n) {
  return strcmp(n, "jpos") == 0 || strcmp(n, "jmove") == 0 || strcmp(n, "jvel") == 0 ||
         strcmp(n, "home") == 0;
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
  if (strcmp(cmd.name, "set") == 0) {  // set,<_>,0 clears the e-stop latch (mirrors AVR/ESP32)
    if (cmd.argc >= 1 && (int)cmd.args[0] == 0) estopped = false;
    pibot_build_ack(cmd.seq, out, sizeof(out));
    send_line(out);
    return;
  }
  if (strcmp(cmd.name, "enable") == 0) {
    drivers_enable(cmd.argc >= 1 && (int)cmd.args[0] != 0);
    pibot_build_ack(cmd.seq, out, sizeof(out));
    send_line(out);
    return;
  }
  if (strcmp(cmd.name, "ping") == 0) {
    pibot_build_ack(cmd.seq, out, sizeof(out));
    send_line(out);
    send_state();
    return;
  }
  if (is_motion(cmd.name)) {
    if (estopped) {
      pibot_build_nak(cmd.seq, "estop", out, sizeof(out));
      send_line(out);
      return;
    }
    if (cmd.argc >= 1) {
      uint8_t j = (uint8_t)cmd.args[0];
      if (strcmp(cmd.name, "jpos") == 0 && cmd.argc >= 2) {
        if (j < NJ && !jhomed[j]) { pibot_build_nak(cmd.seq, "nothome", out, sizeof(out)); send_line(out); return; }
        cmd_jpos(j, cmd.args[1], 0.f);
      } else if (strcmp(cmd.name, "jmove") == 0 && cmd.argc >= 3) {
        if (j < NJ && !jhomed[j]) { pibot_build_nak(cmd.seq, "nothome", out, sizeof(out)); send_line(out); return; }
        cmd_jpos(j, cmd.args[1], cmd.args[2]);
      } else if (strcmp(cmd.name, "jvel") == 0 && cmd.argc >= 2) {
        cmd_jvel(j, cmd.args[1]);
      } else if (strcmp(cmd.name, "home") == 0) {
        start_home(j);
      }
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

// ---- Arduino -----------------------------------------------------------------------------------
void setup() {
  HOST.begin(BAUD);
  pinMode(PIN_ENABLE, OUTPUT);
  drivers_enable(true);  // energize and HOLD from boot

  for (uint8_t j = 0; j < NJ; j++) {
    pinMode(JCFG[j].home_pin, INPUT_PULLUP);
    steppers[j] = AccelStepper(AccelStepper::DRIVER, JCFG[j].step_pin, JCFG[j].dir_pin);
    steppers[j].setMaxSpeed(JCFG[j].max_sps);
    steppers[j].setAcceleration(JCFG[j].accel);
    steppers[j].setCurrentPosition(0);  // position is unknown until homed
    jmode[j] = MODE_IDLE;
    jhomed[j] = false;
  }
  last_cmd_ms = millis();
}

void loop() {
  while (HOST.available() > 0) handle_byte((char)HOST.read());

  unsigned long now = millis();
  if (now - last_cmd_ms > WATCHDOG_MS && any_active()) {
    stop_all();  // host went quiet -> halt motion, stay energized (HOLD)
  }

  for (uint8_t j = 0; j < NJ; j++) run_joint(j);

  if (now - last_tlm_ms > TELEMETRY_MS) {
    last_tlm_ms = now;
    send_state();
  }
}
