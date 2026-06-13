# PiBot Control Suite

**PiBot** is a wheeled robot — a Raspberry Pi 5 (8 GB, NVMe SSD) brain driving an
ESP32/Arduino motor controller — and the **PiBot Control Suite** (`pibot`) is the
command-line toolkit that discovers it on the network, provisions and flashes it, drives it
over a safety-gated link (wired or wireless), and watches its health.

One operator, one robot, one CLI: from a blank SD card to teleoperating the robot with a
latched e-stop and a deadman watchdog, every step is a `pibot` subcommand.

## What it does

- **Discover** the Pi on any subnet (ARP + Raspberry Pi OUI + mDNS/SSH-banner).
- **Provision & flash** OS images (removable media or onboard NVMe over USB-C rpiboot),
  manage the bootloader EEPROM, and embed your SSH key for a passwordless first boot.
- **Control** the robot through a CRC-framed protocol over a pluggable transport — USB
  serial, Wi-Fi/TCP (ESP32), Bluetooth (BLE / RFCOMM), I²C, or GPIO-UART — every command
  clamped, rate-limited, and e-stop-gated.
- **Operate** with live teleop, scripted motion (`pibot play`), and a telemetry monitor.
- **Deploy** the on-Pi agent (`pibotd`) as a systemd service with health-gated,
  rollback-able releases.

The robot never trusts its link: a dropped connection trips the host deadman watchdog and,
independently, the firmware's own watchdog — so the robot stops even when the Pi can't tell
it to. See [docs/runbooks/e-stop.md](docs/runbooks/e-stop.md).

## Install

```bash
git clone <repo> pibot && cd pibot
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/pibot --help
```

Python 3.11+. Wireless extras are optional and installed on the robot:
`pip install 'pibot[ble]'` (bleak) / `pip install 'pibot[i2c]'` (smbus2).

## Quickstart: discover → connect → teleop → flash

```bash
pibot discover                       # find the robot on the network
pibot keys install pibot             # passwordless SSH (one password prompt)
pibot agent start pibot              # launch the on-Pi control agent (pibotd)
pibot teleop pibot                   # WASD/arrows drive, space = e-stop, q = quit
pibot monitor pibot                  # live SoC + robot telemetry, threshold alerts
```

To bring up a fresh Pi from a blank disk, see [docs/runbooks/flash.md](docs/runbooks/flash.md)
and [docs/runbooks/first-boot.md](docs/runbooks/first-boot.md).

## Safety first

Any state-changing command previews with `--dry-run`; disk/bootloader writes also require
`--confirm` and pass a wrong-disk guard. Stop the robot at any time:

```bash
pibot estop pibot                    # latch e-stop and command a stop
```

## Documentation

- **[docs/usage.md](docs/usage.md)** — every command with examples.
- **Runbooks** — [flash](docs/runbooks/flash.md) ·
  [first-boot](docs/runbooks/first-boot.md) ·
  [e-stop](docs/runbooks/e-stop.md) ·
  [eeprom-recovery](docs/runbooks/eeprom-recovery.md) ·
  [wireless-bringup](docs/runbooks/wireless-bringup.md) ·
  [nebula-overlay](docs/runbooks/nebula-overlay.md) ·
  [mission-control](docs/runbooks/mission-control.md)
- **[docs/specs/SPEC-1-pibot-control-suite.md](docs/specs/SPEC-1-pibot-control-suite.md)** —
  the full specification.
- **[firmware/README.md](firmware/README.md)** — the ESP32/Arduino firmware and wiring.

## Development

```bash
bash scripts/check.sh                # ruff + format + mypy + pytest (coverage-gated)
```

Hardware-marked tests (`-m hardware`) run only when `PIBOT_TEST_HOST` points at a real Pi;
they skip cleanly in CI. CI runs the same gate plus an `arduino-cli` firmware compile.
