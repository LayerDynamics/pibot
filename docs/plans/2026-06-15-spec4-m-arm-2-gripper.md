# Plan — M-ARM-2: Gripper / end-effector (SPEC-4)

> **Status: software + firmware shipped (2026-06-15); ⬜ hardware bench-verify pending.** Tasks
> 2.1–2.4 complete and 2.5 docs done: firmware `grip`/`tool` verbs + `grip` telemetry (STM32 compiles
> with `Servo.h` — 42708 B as-shipped opt-out, ~45 KB with the gripper enabled), codec schemas,
> `ArmManager.grip/tool` + gripper telemetry, full surface
> (`/arm/control`, `AgentClient`/`RobotLink`, `POST /api/arm/{grip,tool}`, `pibot arm grip|tool`,
> `Arm.tsx` gripper control), `scripts/check.sh` + desktop gate green. **Outstanding (hardware, user):**
> set the `⬜ TUNE` gripper pins/angles to the real wiring, re-flash with a fresh unique `.bin` name,
> bench-verify servo travel + that e-stop/watchdog still hold. **Both actuators ship opt-in**
> (`HAS_GRIPPER=false`, `HAS_TOOL=false`) so re-flashing a gripper-less arm never attaches the
> servo/claims a timer — set them `true` once the servo/relay is wired and the pin confirmed.
> The remaining bench-signoff work is now tracked in
> [`M-ARM-7`](./2026-06-16-spec4-m-arm-7-hardware-validation-release-hardening.md) and
> [`docs/hardware-arm-signoff.md`](../hardware-arm-signoff.md).
>
> **For Claude:** execute with `lore:execute`. **TDD mandatory** (failing test first → implement →
> `scripts/check.sh` green). Shared decisions/discipline/invariants: see the
> [plan index](./2026-06-15-spec4-robot-arm-implementation.md). **Ask before any `git` commit.**

## Goal

Give the arm an end-effector: a servo gripper on the spare **E0** channel (no endstop needed) plus an
optional digital-output for a pneumatic/relay tool, controllable through the M-ARM-1 surface and
reported in telemetry. Firmware safety stays unchanged.

## Realizes

- SPEC-4 **FR-7, FR-8**; closes `OtherArms.md` **§6B-2** (no gripper / end-effector).

## Depends on / blocks

- **Depends on:** M-ARM-1 (the gripper commands ride the control surface, CLI, and UI).
- **Blocks:** nothing hard; gripper steps become available to M-ARM-5 programs (`grip`/`tool` step kinds).

## Prerequisites (⬜ confirm with the user before 2.1)

- Gripper **servo channel/pins** on the board (E0 step/dir repurposed to servo PWM, or a dedicated PWM
  pin), servo **min/max angle**, and the optional **pneumatic digital-output pin**.

## Tasks

### 2.1 — Firmware verbs

- **What:** in `firmware/pibot_arm_stm32` (`.ino` + `protocol.{h,cpp}`), add `grip,<deg>` (servo PWM on
  the E0 channel, angle-clamped from a gripper config block) and `tool,<0|1>` (digital output). Include
  the gripper position in the telemetry frame. **Do not touch** the existing e-stop/watchdog/soft-limit
  logic.
- **Files:** `firmware/pibot_arm_stm32/pibot_arm_stm32.ino`, `firmware/pibot_arm_stm32/protocol.{h,cpp}`.
- **Test-first:** echo-stand round-trip (toolchain-marked) asserting `grip`/`tool` parse + ack and the
  telemetry frame carries the gripper field.
- **Done when:** STM32 compiles; echo-stand round-trip green for the new verbs.

### 2.2 — Host codec

- **What:** register `grip` and `tool` command schemas in `pibot/protocol/codec.py` (mirror the
  firmware arg order).
- **Files:** `pibot/protocol/codec.py`.
- **Test-first:** extend `tests/test_arm_protocol.py` — encode/decode round-trip for `grip`/`tool`,
  including a bad frame → `DecodeError` (never crash).
- **Done when:** codec round-trips the verbs; gate green.

### 2.3 — ArmManager methods

- **What:** add `ArmManager.grip(deg)` and `ArmManager.tool(on)` routing to the owning board.
- **Files:** `pibot/arm/manager.py`.
- **Test-first:** extend `tests/test_arm_manager.py` (correct frame to the correct board).
- **Done when:** manager routes the verbs; gate green.

### 2.4 — Surface the gripper

- **What:** thread `grip`/`tool` through the M-ARM-1 surface — `/arm/control` frames, `AgentClient` +
  `RobotLink` methods (`arm_grip`, `arm_tool`), `POST /api/arm/{grip,tool}`, `pibot arm grip|tool`, and
  an Arm-screen gripper control (slider/open-close + tool toggle). Gripper commands pass the host gate
  (e-stop-latched → refuse).
- **Files:** `agent/app.py`, `pibot/control/client.py`, `pibot/mc/robot_link.py`,
  `pibot/mc/routes_arm.py`, `pibot/cli.py`, `app/src/screens/Arm.tsx`, `app/src/stores/armStore.ts`.
- **Test-first:** extend `tests/test_agent_arm.py`, `tests/test_mc_arm.py`, `tests/test_cli_arm.py`,
  `app/src/stores/armStore.test.ts`.
- **Done when:** gripper controllable from CLI + UI and present in telemetry; gates green.

### 2.5 — Re-flash + docs

- **What:** ⚠️ firmware re-flash required — **unique `.bin` name** per `CLAUDE.md`'s SD-card rule;
  bench-verify e-stop + watchdog still hold after the flash. Update `CLAUDE.md`'s firmware-verb list and
  mark `OtherArms.md` §6B-2 shipped.
- **Files:** `CLAUDE.md`, `docs/research/stepper-robot-arms-github/OtherArms.md`,
  `firmware/pibot_arm_stm32/sd/README.md` (note the new verbs).
- **Done when:** docs accurate (NFR-8); hardware bench-verified.

## Milestone DoD

Gripper controllable from CLI and the Arm screen, present in telemetry; echo round-trip green;
e-stop/watchdog re-verified on hardware after re-flash; `scripts/check.sh` + desktop gate green.

## Notes / risks

- E0 has no endstop — rely on firmware **angle clamps** from config and conservative defaults to prevent
  servo over-travel (SPEC R6). Bench-verify travel before closing.
- Keep the gripper out of the homing/soft-limit joint loop — it is a separate actuator, not a homed joint.
