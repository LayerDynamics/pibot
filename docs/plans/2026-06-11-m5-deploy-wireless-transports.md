# Plan — M5: Deploy & Remaining Wireless Transports

| | |
|---|---|
| **Spec** | [SPEC-1](../specs/SPEC-1-pibot-control-suite.md) §4.1 FR-7, FR-4.1 (rfcomm/ble/i2c/uart) |
| **Milestone** | M5 |
| **Depends on** | M4 |
| **Branch** | `m5-deploy-wireless-transports` |
| **Date** | 2026-06-11 |
| **Status** | ✅ Shipped (commit `107e389`) |

> Conventions per the
> [roadmap](2026-06-11-pibot-control-suite-roadmap.md#shared-conventions-apply-to-every-task-in-every-milestone).
> TCP/Wi-Fi already shipped in M3; this milestone adds the **remaining** transports
> (RFCOMM, BLE, I²C, GPIO-UART) and the repeatable deploy pipeline.

## Goal
Make the suite operationally complete: repeatable code deploy with `systemd`, venv,
health-check and rollback; and the remaining `Transport` backends so the robot can be
driven over Bluetooth-Classic, BLE, I²C, and GPIO-UART — plus scripted motion (`play`).

## In scope
`pibot deploy` (rsync + systemd + venv + rollback), `RfcommTransport`, `BleTransport`,
`I2CTransport`, GPIO-`uart` finalization, `pibot play`.

## Out of scope
Final hardening/docs/security pass (M6).

## Prerequisites
- M4 (the agent + transport ownership it deploys).
- For BLE: `bleak`; for I²C: `smbus2`; pinned in the Pi-side `requirements.txt`.

## Tasks

### T5.1 — `pibot deploy` payload sync
- **Files:** `pibot/deploy/sync.py`, `deploy/.deployignore`
- **Test first:** `tests/test_deploy_sync.py` — rsync argv syncs the `robot/` subtree
  and **excludes host-only tooling** (`tools/`, host CLI, tests, docs); reports a diff
  of changed files; `--dry-run` writes nothing.
- **Implement:** rsync-based payload sync into a timestamped `releases/<ts>/` dir on the
  Pi with a `current` symlink (atomic swap).
- **Done when:** include/exclude + diff + dry-run tests green.

### T5.2 — Agent service install + restart + rollback
- **Files:** `pibot/deploy/service.py`, `deploy/pibotd.service`
- **Test first:** `tests/test_deploy_service.py` — generates the `pibotd.service` unit
  (venv exec path, restart-on-failure, journald); builds commands to create/refresh the
  Pi-side venv (`python -m venv`, `pip install -r`), `systemctl daemon-reload`/`enable`/
  `restart`, then `/health` check; `--rollback` repoints `current` to the previous
  release and restarts.
- **Implement:** service install/update, venv provisioning, restart+healthcheck,
  rollback (symlink swap).
- **Done when:** unit tests green; integration `deploy --restart` against the Pi brings
  the agent up and `/health` passes (hardware-marked).

### T5.3 — `RfcommTransport` (Bluetooth Classic)
- **Files:** `pibot/transport/rfcomm.py`
- **Test first:** `tests/test_transport_rfcomm.py` — reuses the **serial pty-loopback
  contract** (RFCOMM presents as `/dev/rfcomm*`, a serial device), plus the bind/release
  command construction (`rfcomm bind`) is unit-tested.
- **Implement:** thin subclass of `SerialTransport` targeting `/dev/rfcomm0` + bind
  helper.
- **Done when:** contract + bind tests green.

### T5.4 — `BleTransport` (BLE, Nordic-UART style)
- **Files:** `pibot/transport/ble.py`
- **Test first:** `tests/test_transport_ble.py` — against a **fake bleak client**:
  connect to address + RX/TX characteristics, notify→`recv`, write→`send`, partial-
  packet reassembly, disconnect → `is_open` False + fail-safe.
- **Implement:** `bleak`-based backend (async) implementing the `Transport` contract.
- **Done when:** fake-bleak contract + disconnect tests green.

### T5.5 — `I2CTransport` + GPIO-UART finalization
- **Files:** `pibot/transport/i2c.py`, `pibot/transport/serial.py` (uart params)
- **Test first:** `tests/test_transport_i2c.py` (fake `smbus2` bus: register/stream
  framing, read/write, NAK on bus error); `tests/test_uart_config.py` (UART selects
  `/dev/serial0`, requires `enable_uart=1`, documents the 3.3 V↔5 V level shifter).
- **Implement:** smbus2-backed I²C transport + UART parameterization of the serial
  backend.
- **Done when:** I²C fake-bus + UART config tests green; level-shifter requirement
  documented in `firmware/README.md`.

### T5.6 — `pibot play` (scripted motion)
- **Files:** `pibot/control/sequence.py`
- **Test first:** `tests/test_play.py` — parse a motion `sequence.yaml`
  (`{at: seconds, cmd, args}`); scheduler dispatches commands at the right times
  through the **same safety gates** (clamp, e-stop honored, watchdog kept alive);
  malformed sequence → clear error; e-stop aborts the sequence.
- **Implement:** YAML loader + timed dispatcher routed through the agent control path.
- **Done when:** parse + scheduling + safety-abort tests green.

### T5.7 — Integration + E2E (hardware-marked)
- **Files:** `tests/integration/test_deploy_live.py`,
  `tests/e2e/test_wireless_drive_e2e.py`
- **Test:** `deploy --restart` updates and health-checks the agent on the Pi; **at
  least one wireless backend (BLE or RFCOMM) drives the real robot**; `--rollback`
  restores the prior release; the wireless drop-to-stop fail-safe holds.
- **Done when:** integration green vs the Pi; one wireless E2E recorded on hardware.

## Milestone acceptance criteria (SPEC-1 §8 M5)
- `pibot deploy --restart` updates and health-checks the agent.
- At least one wireless backend drives the robot (BLE/RFCOMM; TCP already in M3).
- `--rollback` restores the previous release.
- All gates green.

## Risks
- **Deploy bricking the running agent** → atomic symlink swap + rollback + post-deploy
  `/health` gate; deploy is idempotent.
- **BLE/RFCOMM latency/jitter for motion** → safety watchdog + firmware backstop;
  wireless drop tests assert fail-safe; clamp rates.
- **I²C bus contention/level issues** → agent sole-owner; documented wiring/level
  requirements.

## Definition of done
All gates pass; acceptance met; deploy+rollback proven; ≥1 wireless drive demonstrated
on hardware with fail-safe; branch ready to commit (ask first).
