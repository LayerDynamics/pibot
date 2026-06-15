# Plan — PiBot Robot Arm (5–6 DOF stepper arm on Creality boards)

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` per phase. **Plan/design doc** — confirm the
> hardware blanks (marked ⬜) with the user before implementing a phase.
> **Scope guard:** Build phase-by-phase; do not jump ahead. Each phase is independently shippable.

**Goal:** Drive a **5–6 joint stepper robot arm** from the AI/Pi, using the user's **Creality 4.2.2
(STM32F103)** boards as the joint controllers, with **custom PiBot firmware** (not Marlin). The
control model is intentionally left open, so the design is **layered and modular**: the firmware stays
joint-level (position + velocity + safety); all kinematics/coordination/IK live in swappable **host**
layers above it.

**Why custom firmware (B), not Marlin:** the user chose B. Trade-off acknowledged — Marlin is built
for planned multi-axis position moves (good for arms), so B means re-implementing acceleration-planned
joint motion. We mitigate by using the proven `AccelStepper` library on-board and keeping the firmware
deliberately small (per-joint primitives only); the "smart" motion lives on the host where it's easy
to iterate.

## Architecture — five layers (each swappable)

```
[ AI / teleop / Mission Control ]      ← intent (poses, gestures, jog)
            │
[ Kinematics layer  (host, pluggable) ] ← IK/FK; START: pass-through (direct joint), ADD LATER: IK
            │  logical joint targets (angle / velocity)
[ Arm manager       (host: pibot.arm) ] ← maps logical joints → (board, channel); trajectories; limits
            │  per-board joint frames over serial
[ Joint firmware    (Creality 4.2.2)  ] ← AccelStepper per joint: position + velocity + homing + safety
            │  step/dir/enable
[ Stepper drivers + joints (hardware)  ]
```

The **firmware↔host boundary is the contract**: the firmware never knows about "the arm", only its own
N joints. Swap the kinematics layer (pass-through → IK → learned policy) without touching firmware.

## Hardware (⬜ = confirm with user)
- **Boards:** 2× **Creality 4.2.2** (STM32F103RE, 4 channels each = 8; use 5–6). Each is one
  "joint controller", connected to the Pi over **UART via its onboard USB-serial** (4.2.2 has *no*
  native USB). Two boards → two `/dev/tty*` ports.
- **Joint→channel map (per board):** X=`PC2/PB9`, Y=`PB8/PB7`, Z=`PB6/PB5`, E0=`PB4/PB3`; **shared
  ENABLE=`PC3`**. ⬜ joint count (5 or 6), ⬜ which joints on which board.
- **Per joint (config, not code):** steps/rev, microstep, gear ratio, min/max angle, invert,
  home direction + endstop pin, max speed/accel. ⬜ values per joint.
- **Homing/limits — USE BOTH (decided):** every joint homes against a physical **endstop** (absolute
  zero reference) **and** is bounded by firmware **soft limits** (`min_deg`/`max_deg`) so it can never
  drive past its safe range even with a flaky switch. Endstop = truth at home; soft limits = guard
  everywhere else.
  - **Constraint:** a 4.2.2 exposes only **3 min-endstop inputs** (X/Y/Z); the **E0 channel has no
    endstop input**. So put **≤3 homed joints per board** → a **3 + 3** split across the two boards
    cleanly gives all 6 joints a native endstop. (If a board must drive a 4th homed joint, its
    endstop wires to a spare GPIO — ⬜ identify one per board.)
- **Power/e-stop:** ⬜ separate motor PSU; a hardware e-stop that cuts driver power is strongly
  recommended in addition to the firmware e-stop.

## Firmware (custom, modular — `firmware/pibot_arm_stm32/`)
- **Reuse:** PiBot wire protocol (`protocol.{h,cpp}` — CRC-framed, mirrored host-side) + the safety
  invariants (e-stop latch, watchdog, link-loss stop).
- **`Joint` struct (config-driven):** `{step_pin, dir_pin, en_pin, steps_per_rev, gear, invert,
  min_deg, max_deg, max_sps, accel, home_pin, home_dir}`. Joints declared in a CONFIG block →
  add/remove joints by config, not logic.
- **`AccelStepper` per joint**, two modes:
  - **Position:** `moveTo(angle→steps)` clamped to `[min_deg,max_deg]`; `run()` each loop.
  - **Velocity/jog:** `setSpeed(sps)` + `runSpeed()` until a new target or stop.
- **Joint protocol (extensible — new verbs are cheap):**
  - `jpos <id> <deg>` → move joint to angle · `jvel <id> <sps>` → jog · `jstop <id>` · `home <id>`
  - `estop` (latch: disable EN on all + halt) · `set,estop,0` (clear) · `enable <0|1>`
  - telemetry `<… joint positions/limits/moving>` streamed back for host closed-loop.
- **Safety (per-joint + global):** soft limits (refuse/clip out-of-range), e-stop latch, **300 ms
  watchdog** (host quiet → hold position, steppers stay enabled to resist gravity OR disable —
  ⬜ choose per arm), link-loss stop. Homing required before position moves (configurable).
- **Toolchain:** STM32 core for arduino-cli (`STMicroelectronics:stm32`) **or** PlatformIO
  (`genericSTM32F103RE`). Comms on the USART wired to the onboard USB-serial. **Flashing:** the
  4.2.2 has no SWD header exposed by default → flash via **serial bootloader** (BOOT0) or the
  **SD-card `firmware.bin`** method. ⬜ confirm flashing route on first board.

## Host (`pibot/arm/`, modular)
- **`ArmManager`:** logical joints `J0..J5` → `(port, channel)`; opens the 1–2 serial links (reuse
  `pibot.transport.serial`); fans joint commands to the right board; aggregates telemetry.
- **Kinematics (pluggable):** an interface `JointSolver.solve(target) -> joint_targets`.
  - **Phase 1:** `DirectSolver` (pass-through: caller gives joint angles).
  - **Phase 3:** `IKSolver` (Cartesian pose → joints) — drop-in, no firmware change.
- **Reuse** the agent/MC stack: the arm becomes another capability behind `pibotd`; teleop/AI send
  joint or pose intents.

## Phased build order (each phase = a milestone, independently testable)
1. **A.1 — Firmware joint control (one 4.2.2):** `Joint` + `AccelStepper` + `jpos`/`jvel`/`jstop`/
   `home`/`estop`; host echo-stand round-trip; compiles for STM32. *No arm math.*
2. **A.2 — Safety + homing:** soft limits, watchdog hold, homing, e-stop latch. Bench-test one joint.
3. **A.3 — Multi-board ArmManager (host):** drive 5–6 joints across 2 boards by logical id.
4. **A.4 — Trajectories:** coordinated multi-joint moves (synchronized arrival) on the host.
5. **A.5 — Kinematics plug-in:** `DirectSolver` → add `IKSolver`; expose pose control to the AI/MC.

## Definition of done (per phase)
`bash scripts/check.sh` green for host code; firmware compiles for the STM32 target; echo-stand
round-trip passes for the joint protocol; bench-verified motion on real hardware before closing a phase.

## Open questions to resolve before A.1 (⬜)
1. Exact joint count (5 or 6) and which joints land on which board.
2. Per-joint: steps/rev, gear ratio, angle limits, max speed/accel.
3. ~~Endstops?~~ **RESOLVED: both** — endstop homing + soft limits on every joint; **3+3 joint
   split** across the two boards so each homed joint uses a native X/Y/Z endstop input.
4. On watchdog/idle: **hold** (keep enabled, resist gravity) or **release** (disable)? Arm-dependent.
5. Flashing route for the 4.2.2 (serial bootloader vs SD-card `firmware.bin`).
