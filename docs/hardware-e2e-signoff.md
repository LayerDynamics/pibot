# Hardware E2E sign-off (T6.8)

The acceptance bar that **cannot** be met without the physical robot: the full
discover → connect → deploy → teleop → monitor → reflash journey on real hardware. This
page is the checklist and the results record.

> **Status: PENDING — not yet run on hardware.** The automated suite proves the *software*
> stack end-to-end in-process (real client → agent → safety → transport, radio/robot
> faked); it does **not** certify this hardware journey. Per the repo's E2E rule, the CI
> echo-stand is an aid, not a substitute. Do not mark M6's DoD met until the table below is
> filled in on a real Pi + robot.

## Preconditions

- A Pi 5 reachable on the LAN with the suite SSH key installed (`pibot keys install`).
- The ESP32/Arduino flashed with the firmware ([../firmware/README.md](../firmware/README.md))
  and the robot powered with motors connected.
- `PIBOT_TEST_HOST` exported to the Pi's address; for the wireless leg, `PIBOT_TEST_BLE`
  or `PIBOT_TEST_RFCOMM` set to the controller's Bluetooth address.

## Run the hardware-marked tests

```bash
export PIBOT_TEST_HOST=192.168.1.99
export PIBOT_TEST_BLE=AA:BB:CC:DD:EE:FF   # optional: wireless drive leg
.venv/bin/pytest -m hardware -q
```

## Manual journey (record each result)

```bash
pibot discover                       # 1. robot found on the network
pibot run pibot -- uname -a          # 2. passwordless SSH
pibot deploy pibot                   # 3. agent deployed + /health passes
pibot deploy pibot --rollback        # 4. rollback restores the previous release
pibot agent start pibot              # 5. agent serving real telemetry
pibot teleop pibot                   # 6. drive wired; release/drop -> robot stops
pibot monitor pibot --once           # 7. real vcgencmd/psutil telemetry
# 8. reflash the NVMe over USB-C (rpiboot) and boot the new image (runbooks/flash.md)
```

## Results

| # | Step | Status | Date | Notes |
|---|------|--------|------|-------|
| 1 | discover | ⬜ pending | | |
| 2 | passwordless SSH | ⬜ pending | | |
| 3 | deploy + health | ⬜ pending | | |
| 4 | rollback | ⬜ pending | | |
| 5 | agent telemetry | ⬜ pending | | |
| 6 | teleop + drop-to-stop (wired + ≥1 wireless) | ⬜ pending | | |
| 7 | monitor real telemetry | ⬜ pending | | |
| 8 | reflash NVMe + boot | ⬜ pending | | |

## Verify

The in-process E2E (software stack, no hardware) is the standing proxy and must stay green:

```bash
.venv/bin/pytest tests/e2e -q
```
