# Hardware Arm Sign-off (M-ARM-7)

The acceptance bar that **cannot** be met without the physical Pi + arm stand: the full
home/jog/move/program/twin/e-stop/deploy journey on real arm hardware.

> **Status: PENDING — software complete, bench signoff not yet recorded.** The automated and
> host-local suites prove the software stack is wired correctly; they do **not** certify the
> physical arm's wiring, safe motion envelope, deploy/rollback behavior on the bench, or the
> Mission Control arm workflow against a real stand.

## Preconditions

- A Pi reachable on the LAN with the suite SSH key installed.
- `pibotd` deployed on that Pi with an arm configured and powered.
- A clear, obstruction-free bench envelope.
- Optional hardware/features recorded before running:
  - gripper/tool installed or absent
  - `[arm-ik]` installed or absent
  - safe joint / motion targets for the live smoke

## Bench environment

```bash
export PIBOT_TEST_HOST=192.168.1.99
export PIBOT_TEST_ARM=1
export PIBOT_TEST_TOKEN="$(cat ~/.config/pibot/agent.token)"   # optional override if needed
export PIBOT_TEST_ARM_HOME_JOINT=0
export PIBOT_TEST_ARM_MOVE_DEG=5
export PIBOT_TEST_ARM_MOVE_SPEED=5

# Optional capability flags for the same stand:
export PIBOT_TEST_ARM_GRIPPER=1    # only when the optional gripper/tool hardware is fitted
export PIBOT_TEST_ARM_IK=1         # only when the robot has the [arm-ik] extra installed
```

## Hardware-marked pytest

```bash
.venv/bin/pytest tests/integration/test_arm_live.py -q
.venv/bin/pytest tests/integration/test_deploy_live.py -q
```

## Manual CLI journey

```bash
pibot arm telemetry pibot
pibot arm home pibot 0
pibot arm jog pibot 0 10
pibot arm move pibot 0 5 --speed 5
pibot arm pose-save pibot bench-ready
pibot arm program-list pibot
pibot arm program-run pibot bench-smoke
pibot arm program-stop pibot
pibot arm estop pibot
pibot arm clear pibot
pibot deploy pibot
pibot deploy pibot --rollback
```

## Manual Mission Control journey

See [`app/e2e/arm.e2e.ts`](../app/e2e/arm.e2e.ts) and [`app/e2e/README.md`](../app/e2e/README.md).
Build the debug app, connect to an arm-enabled stand, and execute the recorded Arm-tab flow.

## Results

### Live smoke / safety

| # | Step | Status | Date | Notes |
|---|------|--------|------|-------|
| 1 | `/arm/telemetry` reports enabled arm + sane joint data | ⬜ pending | | |
| 2 | E-stop latches and clear releases it | ⬜ pending | | |
| 3 | Enable / disable behaves as expected on the bench | ⬜ pending | | |
| 4 | One conservative joint homes successfully | ⬜ pending | | |
| 5 | Short jog pulse moves the expected joint and stops on release | ⬜ pending | | |
| 6 | Conservative absolute move succeeds after homing | ⬜ pending | | |

### Optional capabilities

| # | Step | Status | Date | Notes |
|---|------|--------|------|-------|
| 7 | Gripper/tool smoke (if installed) | ⬜ pending | | |
| 8 | Cartesian move / `moveL` smoke (if `[arm-ik]` installed) | ⬜ pending | | |

### Persistence / twin / release

| # | Step | Status | Date | Notes |
|---|------|--------|------|-------|
| 9 | Pose save/list/get/delete works on the Pi | ⬜ pending | | |
| 10 | Program save/run/stop/delete works on the Pi | ⬜ pending | | |
| 11 | Arm-screen 3-D twin tracks telemetry live | ⬜ pending | | |
| 12 | Arm-screen host-marked E2E flow passes | ⬜ pending | | |
| 13 | `pibot deploy` preserves the arm surface | ⬜ pending | | |
| 14 | `pibot deploy --rollback` preserves the arm surface | ⬜ pending | | |

## Verify

The normal software gate must remain green alongside the hardware signoff:

```bash
./scripts/check.sh
```
