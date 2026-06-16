# Runbook — Operating the stepper arm (M-ARM-1)

How to home, jog, move, pose, and e-stop the stepper arm from the CLI or Mission Control, and
how to recover after an e-stop. Every motion command passes through **two independent safety
layers**: the host arm gate (`pibot/arm/safety.py`) and the firmware's own gate (soft limits,
latched e-stop, homing-before-`jpos`) — so a bug in either still leaves the other in force.

> Prerequisite: an arm is configured on the robot (`arm_serial_ports` / `arm_joints_per_board`
> in `~/.config/pibot/config.toml`) and `pibotd` is running. With no arm configured, the arm
> routes return cleanly ("no arm configured") and Mission Control's Arm screen shows the same.

## The golden sequence: home → jog → pose → e-stop

```bash
pibot arm telemetry pibot              # confirm the arm is enabled and see per-joint angles
pibot arm home pibot --all             # 1. HOME every joint against its endstop (required first)
pibot arm jog pibot 0 15               # 2. JOG joint 0 at +15 deg/s (hold-to-move from the UI)
pibot arm move pibot 1 45              # 3. MOVE joint 1 to an absolute 45° (needs J1 homed)
pibot arm move-all pibot 0=30,1=-20 --seconds 2   #    or move several, arriving together
pibot arm pose pibot zero              #    drive the built-in all-joints-zero preset
pibot arm estop pibot                  # 4. E-STOP — latches; all motion refused until cleared
```

**Homing is mandatory before absolute moves.** Until a joint is homed, `move`/`move-all`/`pose`
are refused by the host gate (`nak: joint N not homed`) *and* by the firmware (`nak nothome`).
Velocity **jog** does not require homing (the firmware applies soft limits only once homed), so
jogging is how you bring an un-homed joint off an endstop or verify wiring.

Add `--dry-run` to any motion verb to print the intent and send nothing:

```bash
pibot arm move-all pibot 0=90,1=-45 --seconds 2 --dry-run
```

### From Mission Control

Open the **Arm** screen while connected. Each joint has `−`/`+` jog buttons (hold to move,
release to stop), a **Home** button, a go-to-angle field with **Go** (disabled until the joint
is homed), and a homed indicator. The whole-arm **E-Stop** button is always visible and latches;
jog buttons lock out while the latch is set.

## E-stop and recovery

The arm e-stop **latches**: once set, every motion command (`jpos`/`jmove`/`jvel`/`home`/`move`)
is refused until you explicitly clear it. The latch lives on `pibotd` (shared across the CLI, the
app, and reconnects), so a second operator sees it latched too.

```bash
pibot arm estop pibot      # latch — motion now naks with "estop latched"
pibot arm clear pibot      # clear the latch — motion is accepted again
```

Recovery checklist after an e-stop:

1. Make the cause safe (clear the obstruction, fix the wiring) before clearing.
2. `pibot arm clear pibot` to release the latch.
3. Re-check `pibot arm telemetry pibot` — homing **survives** an e-stop (the latch refuses
   motion but does not un-home joints), so you usually do **not** need to re-home.
4. Resume jogging/moving.

> `jstop` (stop one joint, hold position) and `enable`/`disable` (energize/release the steppers)
> are permitted even while latched — they reduce or hold state, they don't actuate into motion.

> **Caveat — `disable` loses position truth.** Motion is open-loop (no encoders): position is
> "homed + commanded steps." Releasing the steppers (`disable`, or a power cycle) lets the arm be
> back-driven by hand, after which the commanded position no longer matches reality. Neither the
> host nor the firmware clears the homed flag on `disable`, so the homed indicator may then
> **overclaim**. Re-home (`pibot arm home pibot --all`) after any disable/back-drive before
> trusting absolute moves. The homed indicator means "home was commanded", not "position verified."

## Gripper / end-effector (M-ARM-2)

A servo gripper rides the spare **E0** channel; an optional digital-output **tool** (relay/pneumatic)
rides a configurable pin. Both go through the same host gate — **refused while e-stop is latched** —
and the gripper angle is clamped to the servo range on the host and to the configured
`[GRIP_MIN_DEG, GRIP_MAX_DEG]` on the board. The gripper has **no endstop**, so those clamps + a
conservative `GRIP_MAX` are the only over-travel guard — bench-verify travel before closing on
anything.

```bash
pibot arm grip pibot 0       # open (servo to 0°)
pibot arm grip pibot 30      # close to 30° (board clamps to GRIP_MAX)
pibot arm tool pibot on      # energize the tool relay (off to release)
```

From Mission Control, the **Arm** screen's Gripper row has a slider + **Open**/**Close** buttons and a
**Tool** toggle; the readout shows the live servo angle + tool state from telemetry. The gripper ships
**opt-in**: firmware `HAS_GRIPPER`/`HAS_TOOL` default `false`, so until you enable them `grip`/`tool`
nak and the screen shows no gripper. Set them `true` and confirm the `⬜ TUNE` pins/angles
(`GRIP_PIN`, `GRIP_MIN_DEG`, `GRIP_MAX_DEG`, `TOOL_PIN`) on the bench when you flash — see
[`firmware/pibot_arm_stm32/sd/README.md`](../../firmware/pibot_arm_stm32/sd/README.md).

## Teach / playback programs (M-ARM-5)

The agent can persist named **poses** and **programs** on the Pi, then replay them through the
same host gate + firmware gate as every other arm command. Programs are **abortable**: `program-stop`
or an arm e-stop halts playback mid-run before the next frame or step is sent.

Record the current joint snapshot as a named pose:

```bash
pibot arm pose-save pibot ready
pibot arm pose-list pibot
```

Programs live as JSON under the agent arm state dir:

- default: `~/.pibot/arm/poses/*.json`
- default: `~/.pibot/arm/programs/*.json`

Mission Control's **Arm** screen is the easiest authoring surface: record poses, stage an ordered
step list, save the program, then run/stop it while the screen shows live step progress. The
program model supports:

- `moveJ` — joint-space trapezoidal trajectory to a recorded pose
- `moveL` — Cartesian-linear path with SLERP orientation to a pose with Cartesian data
- `grip`
- `tool`
- `wait`
- `loop`

Run or stop a saved program from the CLI:

```bash
pibot arm program-list pibot
pibot arm program-run pibot pick
pibot arm program-stop pibot
```

`moveL` requires the optional `pibot[arm-ik]` extra and an in-tree arm model; without that, the
runner refuses the step with a clean "IK unavailable" error and the rest of the agent keeps serving.

Operational notes:

1. Playback uses `ArmManager.run_trajectory()` under `asyncio.to_thread`, so the event loop stays
   responsive while a program runs.
2. Recorded poses store the current joint angles and, when FK is available, the current Cartesian
   pose too; that is what enables later `moveL` steps.
3. A stopped or failed run leaves the last program status in telemetry so the UI can surface why
   playback ended.

## Hardware signoff / release gate (M-ARM-7)

Bench signoff is a **separate** bar from the normal software gate. Use the dedicated signoff page to
record the real-hardware evidence for the arm stack:

- [`docs/hardware-arm-signoff.md`](../hardware-arm-signoff.md) — bench environment, hardware-marked
  pytest commands, manual CLI/Mission Control journeys, and the results tables.
- [`app/e2e/arm.e2e.ts`](../../app/e2e/arm.e2e.ts) — the host-marked Arm-screen flow for the Tauri app.

Typical bench env:

```bash
export PIBOT_TEST_HOST=192.168.1.99
export PIBOT_TEST_ARM=1
export PIBOT_TEST_ARM_MOVE_DEG=5
.venv/bin/pytest tests/integration/test_arm_live.py -q
.venv/bin/pytest tests/integration/test_deploy_live.py -q
```

Add `PIBOT_TEST_ARM_GRIPPER=1` when the optional gripper/tool hardware is fitted.

## Per-joint limits

The host gate clamps each absolute angle to `[min_deg, max_deg]` and each velocity to `±max_dps`
**before** the command leaves the Pi; the firmware re-clamps to its own tuned per-joint soft
limits on-board. Configure the host limits with one triple per logical joint:

```toml
# ~/.config/pibot/config.toml
arm_joint_limits = [[-180, 180, 90], [-90, 90, 60], [-90, 90, 60]]  # [min_deg, max_deg, max_dps]
```

The triple count must equal the joint total (`pibotd` refuses to start otherwise). Omit
`arm_joint_limits` to get permissive defaults (`[-180, 180, 90]` per joint) while the firmware
enforces the real bounds.

## See also

- [e-stop.md](e-stop.md) — the robot-drive e-stop and the layered fail-safe model.
- [hardware-arm-signoff.md](../hardware-arm-signoff.md) — the arm hardware release checklist.
- [`docs/usage.md`](../usage.md) — the full `pibot arm` command reference.
- [`docs/specs/SPEC-4-pibot-robot-arm.md`](../specs/SPEC-4-pibot-robot-arm.md) — requirements.
