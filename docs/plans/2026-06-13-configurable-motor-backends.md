# Plan — M13: Configurable Motor Backends (servo / DC / stepper)

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. Note adjacent issues as TODOs; do NOT fix them.

**Goal:** Let one firmware binary drive any of several locomotion hardware types — DC
H-bridge (today), continuous-rotation servos (PCA9685), and stepper motors (step/dir
drivers and ULN2003 unipolar) — selected **at runtime** over the existing protocol, on
ESP32 (primary) and Arduino, with the Pi host able to configure it. Every existing safety
invariant (clamp, e-stop latch, 300 ms watchdog, ESP32 link-loss stop) holds for **all**
backends.

**Architecture:** A `MotorBackend` interface (`begin/drive/motor/stop/tick`) sits behind the
unchanged `apply_drive`/`apply_motor`/`stop_all` actuation seam; the active backend is chosen
by a persisted `MotorConfig` (NVS on ESP32, EEPROM on AVR), defaulting to `hbridge` =
today's exact behavior (backward-compatible). Steppers are driven by a step generator
(ESP32 hardware-timer ISR; AVR Timer1) where step rate ∝ |velocity|; `stop()` halts the
generator so the watchdog/e-stop/link-loss guards all still halt the robot.

**Wire format — NO change to the fuzz-hardened parser.** The firmware parses every arg as a
`float` (`protocol.cpp:67` `atof`), so config travels as the existing `set,<id>,<value>`
command with **numeric param IDs** (host maps dotted names → IDs as CLI sugar). Many small
`set` frames accumulate into the firmware's `MotorConfig`; `set,<APPLY>,1` commits + persists
+ re-inits the backend. A `motorcfg` telemetry frame echoes the active config for readback.

**Tech Stack:** existing `pibot/protocol/codec.py` + firmware `protocol.{h,cpp}` (unchanged);
ESP32 Arduino-core 3.x (LEDC, `Preferences`, `esp_timer`/`hw_timer`); AVR (`Servo`,
`EEPROM`, Timer1); `pibot/config.py`, `pibot/control/oneshot.py`, `pibot/cli.py`.

**Practices:** TDD + typed-first + contract-first. No-hardware default: host unit tests +
echo-stand round-trip; firmware is compile-checked (`toolchain` marker).

| | |
|---|---|
| **Spec** | SPEC-1 (Control Suite) — firmware/protocol/control; extends `firmware/README.md` |
| **Depends on** | current ESP32/Arduino firmware + `set` command + echo-stand harness |
| **Branch** | `m12-2-teleop-estop-video` (current) or a new `m13-configurable-motors` |
| **Date** | 2026-06-13 |
| **Status** | PLANNED — design corrected after advisor review (numeric param IDs; float-only firmware args confirmed at `protocol.cpp:67`). Awaiting first-slice confirmation. |

## In scope
The `MotorBackend` abstraction + 4 backends (hbridge, servo-CR, stepper step/dir, stepper
ULN2003); the numeric param-ID `set` config + persistence + `motorcfg` readback on ESP32 and
Arduino; the host `pibot motor` CLI + `[motor]` config + agent push-on-connect; the
echo-stand round-trip for `set,<id>,<v>`; `firmware/README.md` + a runbook note.

## Out of scope
Closed-loop encoder velocity control; per-wheel PID; MC desktop UI for motor config (host
CLI only this milestone); non-differential kinematics (omni/mecanum); changing the `drive`
semantics (`v`,`w` stay identical).

## Wire contract — motor-config param IDs (define first)
`set,<id>,<value>` (all numeric). IDs are stable; unknown IDs → NAK `param`.

```
ID   name                 meaning
1    motor.kind           0=hbridge 1=servo_cr 2=stepper_stepdir 3=stepper_uln2003
10   motor.l.pin0         left  pinA  (hbridge:PWM  stepdir:STEP  uln2003:IN1)
11   motor.l.pin1         left  pinB  (hbridge:DIR  stepdir:DIR   uln2003:IN2)
12   motor.l.pin2         left  IN3   (uln2003)
13   motor.l.pin3         left  IN4   (uln2003)
20-23 motor.r.pin0..3     right side, same layout
30   motor.steps_rev      steps/rev (steppers)
31   motor.max_sps        steps/sec at |u|=1 (steppers)
32   motor.invert_l       0/1
33   motor.invert_r       0/1
40   motor.servo.l_ch     PCA9685 channel (servo_cr)
41   motor.servo.r_ch
42   motor.servo.neutral_us  default 1500
43   motor.servo.span_us     default 500  (neutral±span = full reverse/forward)
99   motor.apply          1 = commit + persist + re-init backend
```

## Contracts (firmware — contract-first)
```cpp
enum MotorKind : uint8_t { KIND_HBRIDGE=0, KIND_SERVO_CR=1, KIND_STEPDIR=2, KIND_ULN2003=3 };

struct MotorConfig {                 // persisted to NVS / EEPROM; defaults = today's hbridge
  uint8_t  kind;
  uint8_t  lpin[4], rpin[4];
  uint16_t steps_rev, max_sps;
  uint8_t  invert_l, invert_r;
  uint8_t  servo_l_ch, servo_r_ch;
  uint16_t servo_neutral_us, servo_span_us;
  uint16_t crc;                      // integrity guard for stored config
};

struct MotorBackend {                // the only actuation seam
  void begin(const MotorConfig&);    // configure pins / timers
  void drive(float v, float w);      // differential mix -> per-side command
  void motor(int id, float u);       // raw per-side, u in [-1,1]
  void stop();                       // halt outputs AND any step generator (safety)
  void tick(uint32_t now_us);        // advance steppers; no-op for hbridge/servo
};
```

## Tasks

### M13.1 — Host: numeric param-ID map + `pibot motor` CLI + `[motor]` config (NO firmware)
- **Files:** create `pibot/control/motor.py` (the `PARAM_IDS` map + `motor_config_frames()` that
  yields `Message` `set,<id>,<v>` sequences ending in `apply`); extend `pibot/config.py` with a
  validated `[motor]` block; add `pibot motor set …` + `pibot motor show` to `pibot/cli.py`
  (reuse `oneshot`). Tests: `tests/test_motor_config.py`.
- **Step 1 (failing test):** `motor_config_frames({"kind":"stepper_stepdir", ...})` emits the
  exact `set,<id>,<value>` Messages (right IDs, numeric values, `apply` last); encode→decode
  round-trips through `codec.py` ASCII; an unknown field raises `ConfigError`.
- **Step 2:** implement until green; `bash scripts/check.sh`.

### M13.2 — ESP32: `MotorBackend` + hbridge + servo-CR + stepper step/dir + NVS persistence
- **Files:** `firmware/pibot_esp32/pibot_esp32.ino` (+ `motor_backend.h` if it keeps the .ino
  readable). Route `set,<id>,<v>` into `MotorConfig`; `apply` persists via `Preferences` and
  re-inits; emit `motorcfg` telemetry. Step/dir via `esp_timer` periodic ISR (rate ∝ |u|).
- **Verify:** `pibot firmware build firmware/pibot_esp32 --fqbn esp32:esp32:esp32` compiles;
  host echo-stand round-trip for the `set,<id>,<v>` frames; default (no stored config) =
  byte-identical hbridge behavior to today.

### M13.3 — ESP32: stepper ULN2003 backend
- **Files:** same .ino / `motor_backend.h`. 4-pin half-step coil sequence per side; `tick()`
  advances the sequence at the step rate. Compile + echo-stand.

### M13.4 — Arduino (AVR): same backends within AVR limits
- **Files:** `firmware/pibot_arduino/pibot_arduino.ino`. `EEPROM` persistence; `Servo` for
  servo-CR; Timer1 step generator; document AVR step-rate ceiling. Compile + echo-stand.

### M13.5 — Agent push + docs
- **Files:** `agent/` push the `[motor]` config on link-up (so a reflash/boot re-applies it);
  `firmware/README.md` motor-backend matrix + wiring; a short `docs/runbooks/` note.
- **Verify:** full `bash scripts/check.sh` green; firmware compiles for all sketches.

## Definition of done
`bash scripts/check.sh` green (ruff/format/mypy/pytest≥80%); all firmware sketches compile;
echo-stand round-trip passes for the `set,<id>,<v>` config frames; default-config behavior is
byte-identical to today's hbridge robot (backward-compatible).
