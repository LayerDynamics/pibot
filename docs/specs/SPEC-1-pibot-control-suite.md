# SPEC-1 — PiBot Control Suite

| | |
|---|---|
| **Spec ID** | SPEC-1 |
| **Title** | PiBot Control Suite — discover, provision, deploy, control, and monitor the PiBot robot |
| **Status** | Draft |
| **Author** | Ryan O'Boyle (`durbanpoisonpew@protonmail.com`) |
| **Created** | 2026-06-11 |
| **Target repo** | `/Users/ryanoboyle/pibot` |
| **Primary dev host** | macOS (Apple Silicon), Python 3.14 |
| **Robot platform** | Raspberry Pi 5 (8 GB) + 256 GB NVMe SSD, Arduino actuator/sensor subsystem |

---

## 1. Product thesis

**PiBot is a Raspberry Pi 5–brained, Arduino-actuated mobile robot.** The Pi 5 is the
"brain" (compute, networking, OS, high-level logic); one or more Arduino-class
microcontrollers are the "muscles and nerves" (motor drive, servos, real-time
sensor sampling). The two halves talk over a link that may be USB serial, GPIO
UART, I²C, **or wireless**.

This spec defines the **PiBot Control Suite**: the operator/developer toolkit that
makes that robot *operable from a workstation*. It is the layer between "a Pi on
the bench" and "a robot you drive, update, and trust." It does five things:

1. **Find** the robot on any network (already shipped: `tools/pifinder.py`).
2. **Provision/flash** its OS and firmware — from the Mac over USB-C, to removable
   media, and on the Pi itself (clone/backup/bootloader).
3. **Deploy** robot code and configuration to it, repeatably.
4. **Control** it — stream drive/servo/actuator commands and teleoperate it, with
   hard safety guarantees (e-stop, deadman watchdog).
5. **Monitor** it — live telemetry from both the Pi (temp, throttle, voltage,
   load, services) and the robot's sensors.

The marquee behavior: **`pibot discover` → `pibot connect` → `pibot teleop`**, a
human driving the robot in real time from the Mac, while `pibot monitor` streams
its vitals — and when the SSD needs reimaging, **`pibot flash`** rewrites the
onboard NVMe over a single USB-C cable without disassembly.

This is a tools/operations product, not robot autonomy. Path planning, SLAM, and
vision are explicitly **out of scope** (see §4.2) — the suite is the substrate
those would later run on top of.

---

## 2. Goals and non-goals

### 2.1 Goals

- **G1 — One CLI.** A single `pibot` command with subcommands (`discover`,
  `connect`, `run`, `push`, `pull`, `flash`, `provision`, `eeprom`, `deploy`,
  `teleop`, `monitor`, `agent`) is the primary interface. `tools/pifinder.py`
  keeps working standalone and also backs `pibot discover`.
- **G2 — Hybrid runtime.** Stateless Mac-side CLIs for ops/flash/deploy **plus** a
  long-running on-Pi agent (`pibotd`) for the real-time paths (teleop, telemetry)
  that SSH round-trips cannot serve well. The user selected "all of the above and
  hybrid."
- **G3 — Pluggable robot transport.** A single `Transport` abstraction with
  backends for USB serial, GPIO UART, I²C, **and wireless** (TCP/Wi-Fi bridge,
  Bluetooth-RFCOMM, BLE). The user selected "all of the above but wirelessly if
  possible." One owner of the link (the agent) prevents port contention.
- **G4 — Full provisioning surface.** Host-side `rpiboot` mass-storage flashing +
  `rpi-imager` CLI + removable-media flashing + on-Pi clone/backup + `rpi-eeprom`
  bootloader/`BOOT_ORDER` management. The user selected "All of the above."
- **G5 — Safety first.** Every motion path is gated by an e-stop and a deadman
  watchdog; loss of comms halts the robot. Safety logic lives on the Pi (and is
  mirrored into firmware), never solely on a wireless link.
- **G6 — Robust by construction.** Idempotent operations, explicit confirmations
  for destructive actions (flashing, EEPROM writes), structured logging, and a
  `--json` mode on every read-style command for scripting (matching `pifinder.py`).
- **G7 — Real tests.** Unit + integration + hardware-in-the-loop E2E, with a
  documented Arduino echo-firmware test stand for CI when hardware is absent.

### 2.2 Non-goals

- **N1** — Autonomous navigation, SLAM, computer vision, or ML inference.
- **N2** — A graphical desktop/web app in v1 (the agent exposes an API a GUI
  *could* later use; the v1 client is CLI/TUI).
- **N3** — Multi-robot fleet orchestration (designed not to preclude it; not built).
- **N4** — Designing the robot's electrical/mechanical hardware. The suite adapts
  to whatever Pi↔Arduino wiring exists; it does not specify the motor driver.
- **N5** — Cross-vendor SBC support. Raspberry Pi 5 is the only target board.

---

## 3. Users and use cases

| User | Need | Suite answer |
|---|---|---|
| **Builder (Ryan)** at the bench | Reflash a bricked/iterating NVMe fast | `pibot flash` over USB-C (`rpiboot` + imager) |
| **Operator** driving the robot | Real-time teleop with instant stop | `pibot teleop` (keyboard/gamepad) → `pibotd` |
| **Developer** iterating on robot code | Push code + restart service in one step | `pibot deploy` (rsync + systemd) |
| **Anyone** debugging field issues | See temp/throttle/voltage/sensors live | `pibot monitor` (TUI + `--json`) |
| **Scripts/CI** | Machine-readable status | `--json` on every read command |

### 3.1 Representative scenarios

- **S1 "Drive it."** `pibot discover` finds `pibot.local` → `pibot teleop pibot.local`
  opens a WS session to `pibotd`; arrow keys stream velocity commands to the Arduino
  over the active transport; releasing keys / losing the socket triggers e-stop
  within the watchdog window.
- **S2 "Reflash the SSD."** Robot powered off → USB-C to Mac, hold power button →
  `pibot flash --target nvme --image rpi-os-bookworm.img.xz` runs
  `rpiboot -d mass-storage-gadget64`, waits for the NVMe to enumerate on the Mac,
  verifies the image hash, writes it with `rpi-imager --cli`, and re-applies the
  robot's first-boot config.
- **S3 "Ship new code."** `pibot deploy --restart` rsyncs the repo's `robot/` tree
  to the Pi, installs/updates the `pibotd` systemd unit, and restarts it, then
  health-checks the agent.
- **S4 "Why did it slow down?"** `pibot monitor pibot.local` shows
  `temp 81°C · throttled=0x50000 (soft temp limit) · core 0.91V · /dev/nvme0 71%`
  and the live battery/current sensor feed from the Arduino.

---

## 4. Requirements

### 4.1 Functional requirements

#### FR-1 Discovery (exists, integrate)
- FR-1.1 Reuse `tools/pifinder.py` to locate the robot by Pi OUI / hostname /
  SSH banner; expose as `pibot discover`.
- FR-1.2 Persist discovered hosts to an inventory (`~/.config/pibot/inventory.toml`)
  with a friendly alias (`pibot`), last-seen IP, MAC, and link details.
- FR-1.3 Resolve a target argument as alias → inventory IP → mDNS `.local` → raw
  IP, in that order.

#### FR-2 Connection & SSH ops
- FR-2.1 `pibot connect <target>` opens an interactive SSH shell.
- FR-2.2 `pibot run <target> -- <cmd…>` runs a remote command, streams stdout/stderr,
  propagates exit code; `--json` wraps result.
- FR-2.3 `pibot push <target> <src> <dst>` / `pibot pull` transfer files/dirs
  (rsync when available, scp fallback).
- FR-2.4 `pibot keys install <target>` provisions an SSH keypair for passwordless
  ops (generates a dedicated `~/.ssh/pibot_ed25519` if absent; appends to the Pi's
  `authorized_keys`).
- FR-2.5 `pibot tunnel <target> <localport>:<remotehost>:<remoteport>` opens an
  SSH tunnel (e.g., to reach `pibotd` or a camera stream).
- FR-2.6 All SSH ops accept `--user` (default resolved from the Pi's SSH banner —
  `ubuntu` for Ubuntu, `pi` for Raspberry Pi OS — reusing `pifinder`'s banner logic)
  and `--identity`.

#### FR-3 Provisioning & flashing (all paths)
- FR-3.1 **Host USB mass-storage flash:** `pibot flash --target nvme|sd --image <uri>`
  drives `rpiboot -d mass-storage-gadget64`, waits for the block device to
  enumerate on the host, then writes via `rpi-imager --cli`. On macOS it resolves
  the new `/dev/diskN`, `diskutil unmountDisk`s it, and writes to `/dev/rdiskN`.
  Pi 5 entry into bootloader mode requires **holding the power button while
  connecting USB-C** (there is no nRPIBOOT jumper on Pi 5).
- FR-3.2 **Removable-media flash:** `pibot flash --device /dev/diskN --image <uri>`
  writes directly to an SD card or USB-NVMe enclosure, with `--sha256` verification
  and a post-write verify pass (maps to `rpi-imager --cli [--sha256 H] img dev`).
- FR-3.3 **First-boot config:** after any flash, optionally apply headless config
  to the boot partition: hostname, Wi-Fi (`wpa`/NetworkManager), enable SSH, user,
  authorized key, locale, and `enable_uart=1` when UART transport is selected.
  (rpi-imager's CLI does **not** expose these; the suite mounts the boot partition
  and writes `firstrun.sh`/`custom.toml`/`cmdline.txt` itself.)
- FR-3.4 **On-Pi clone/backup:** `pibot provision clone <target> --to <file.img>`
  produces a shrunk, compressed image of the running NVMe (block copy of mounted
  filesystems via `dd`/`rsync`-to-image, then `--shrink`); `pibot provision restore`
  reverses it.
- FR-3.5 **EEPROM/bootloader:** `pibot eeprom status|update|config|boot-order`
  wraps on-Pi `rpi-eeprom-update -a` / `rpi-eeprom-config --edit` to read/update the
  bootloader and set `BOOT_ORDER` (e.g., NVMe-first `0xf416`). Destructive writes
  require `--confirm`.
- FR-3.6 **Arduino firmware flash:** `pibot firmware flash <sketch.hex|.ino>` builds
  (via `arduino-cli`) and uploads firmware to the connected Arduino — run on the Pi
  (which owns the USB/serial link) over SSH, or directly when wired to the Mac.

#### FR-4 Robot control & teleoperation
- FR-4.1 A `Transport` abstraction (§6.3) with backends: `serial` (USB
  `/dev/ttyACM*`/`/dev/ttyUSB*`), `uart` (GPIO `/dev/serial0`), `i2c` (`smbus2`),
  `tcp` (Wi-Fi/ESP bridge), `rfcomm` (Bluetooth Classic, appears as a serial port),
  `ble` (`bleak`). Backend + parameters chosen by config; default `serial`.
- FR-4.2 A line/frame **command protocol** (§6.4) with sequence numbers, CRC, and
  ACK/NAK, plus a richer JSON variant for capable MCUs (ESP32).
- FR-4.3 `pibot teleop <target>` connects to `pibotd` and maps keyboard (and
  optional gamepad via `pygame`/`evdev`) to velocity/servo commands at a fixed
  send rate (default 20 Hz), showing live state in a TUI.
- FR-4.4 `pibot cmd <target> <command> [args…]` sends a single one-shot command
  (e.g., `pibot cmd pibot drive 0.5 0.0`, `pibot cmd pibot servo pan 90`).
- FR-4.5 **E-stop:** `pibot estop <target>` (and the spacebar in teleop) issues an
  immediate, highest-priority stop that the agent and firmware both honor.
- FR-4.6 **Deadman watchdog:** the agent halts all actuators if no valid command
  arrives within a configurable window (default 300 ms); the firmware enforces its
  own independent watchdog as a backstop.
- FR-4.7 Scripted motion: `pibot play <sequence.yaml>` executes a timed command
  sequence with the same safety gates.

#### FR-5 Telemetry & monitoring
- FR-5.1 The agent samples **Pi health**: SoC temp + throttle flags via `vcgencmd
  measure_temp` / `vcgencmd get_throttled`, core voltage via `vcgencmd measure_volts`,
  CPU/mem/load/disk via `psutil`, and key `systemd` unit states.
- FR-5.2 The agent ingests **robot telemetry** from the Arduino (battery voltage,
  motor current, encoder ticks, IMU, range sensors, user-defined fields) via the
  same transport, decoded by the protocol codec.
- FR-5.3 `pibot monitor <target>` renders a live TUI dashboard and supports
  `--json`/`--csv` streaming and `--once` for snapshots.
- FR-5.4 Threshold alerts (temp ≥ limit, throttled, battery low, agent/transport
  down) surface in `monitor` and as non-zero exit codes for scripting.
- FR-5.5 The agent retains a rolling on-Pi log of telemetry (size-bounded, rotated)
  retrievable via `pibot pull` or an agent endpoint.

#### FR-6 On-Pi agent (`pibotd`)
- FR-6.1 An `asyncio` service exposing a local HTTP + WebSocket API (default bind
  `127.0.0.1:8787`, reached from the Mac via `pibot tunnel` or over the trusted LAN
  with a token).
- FR-6.2 Sole owner of the active `Transport`; serializes all actuator commands;
  enforces e-stop, watchdog, and rate limits centrally.
- FR-6.3 Endpoints: `GET /health`, `GET /telemetry` (snapshot), `WS /telemetry`
  (push stream), `WS /control` (command stream), `POST /estop`, `GET/POST /config`.
- FR-6.4 Auth via a shared bearer token (`~/.config/pibot/agent.token`, mirrored to
  the Pi on deploy); refuses non-loopback connections without a valid token.
- FR-6.5 Ships as a `systemd` unit (`pibotd.service`) installed by `pibot deploy`;
  restart-on-failure; structured journald logging.

#### FR-7 Code deploy
- FR-7.1 `pibot deploy <target>` rsyncs the repo's robot payload (configurable
  `robot/` subtree) to a deploy path on the Pi, excluding host-only tooling.
- FR-7.2 Installs/updates `pibotd.service` and the agent's Python venv/deps
  (`pip install -r` inside a Pi-side venv).
- FR-7.3 `--restart` restarts `pibotd` and health-checks it; `--rollback` restores
  the previous deploy (kept as `releases/` symlink-swapped directories).
- FR-7.4 Deploy is idempotent and reports a diff of what changed.

### 4.2 Non-functional requirements

- **NFR-1 Latency.** Teleop command path (key event → actuator) ≤ 50 ms over LAN/USB
  excluding wireless link variance; agent watchdog resolution ≤ 50 ms.
- **NFR-2 Safety.** No single software fault (crashed client, dropped socket, killed
  agent) may leave actuators energized: each layer fails safe to "stop."
- **NFR-3 Portability.** Host CLI runs on macOS and Linux, Python ≥ 3.11; agent runs
  on Raspberry Pi OS / Ubuntu for Pi (Bookworm-class, Python ≥ 3.11). Standard
  library preferred; third-party deps justified per-module (§9).
- **NFR-4 Idempotence & safety rails.** Flashing/EEPROM/restore require an explicit
  device or `--confirm`; the suite never writes to a disk it cannot confirm is the
  intended target (size/model checks, refuse the system disk).
- **NFR-5 Observability.** Structured logs (`--log-json`), `--verbose`, and a
  `--dry-run` on every state-changing command that prints the exact external
  commands it would run.
- **NFR-6 No secrets in repo.** Tokens/keys live under `~/.config/pibot/`; only
  references are committed.
- **NFR-7 Recoverability.** Every destructive op (flash, clone-restore, EEPROM) has
  a documented recovery path, and clone/backup exists precisely to make reflash safe.

---

## 5. Architecture

### 5.1 Topology

```text
┌────────────────────────── macOS workstation ──────────────────────────┐
│  pibot CLI (Python package `pibot/`)                                   │
│   discover  connect/run/push/pull/keys/tunnel   flash/provision/eeprom │
│   firmware  deploy        teleop/cmd/estop/play        monitor         │
│      │                │                  │                     │        │
│      │ pifinder       │ ssh/scp/rsync    │ WS /control         │ WS /telemetry
│      │ (UDP/ARP/TCP)  │ (paramiko/system)│ (token)             │        │
└──────┼────────────────┼──────────────────┼─────────────────────┼───────┘
       │                │                  │                     │
   LAN / mDNS        SSH :22         pibot tunnel / LAN+token   …
       │                │                  │                     │
┌──────┴────────────────┴──────────────────┴─────────────────────┴───────┐
│  Raspberry Pi 5 (robot brain)                                          │
│   sshd                          pibotd.service (asyncio HTTP+WS)       │
│                                   ├─ Safety (e-stop, watchdog, limits) │
│                                   ├─ Telemetry (vcgencmd, psutil, MCU) │
│                                   └─ Transport (sole owner) ───────────┼──┐
│   rpi-eeprom / NVMe / boot partition (provisioning targets)           │  │
└────────────────────────────────────────────────────────────────────────┘  │
                                                                             │
                         Pi↔Arduino link (pluggable)                         │
        serial(USB) │ uart(GPIO+level-shift) │ i2c │ tcp(Wi-Fi/ESP) │ rfcomm │ ble
                                                                             │
┌────────────────────────────────────────────────────────────────────────┐ │
│  Arduino subsystem (muscles/nerves)  ◄──────────────────────────────────┘ │
│   command parser · independent watchdog · motor/servo drive · sensors      │
└────────────────────────────────────────────────────────────────────────────┘

Out-of-band: Mac ──USB-C──> Pi 5 (power button held) ── rpiboot mass-storage ──>
             NVMe appears as /dev/diskN on Mac ── rpi-imager --cli ── reflash
```

### 5.2 Component map

| Layer | Component | Runs on | Responsibility |
|---|---|---|---|
| Discovery | `pifinder.py` (exists) | Mac | Find Pi on the network |
| Host CLI | `pibot/` package | Mac | All operator commands; thin clients to SSH and the agent |
| Provisioning | `pibot/provision/*` | Mac + Pi | rpiboot, imager, eeprom, clone, firmware |
| Agent | `pibotd` | Pi | Real-time control + telemetry, transport owner, safety |
| Transport | `agent/transport/*` | Pi | Pluggable link to the Arduino |
| Protocol | `protocol.py` (shared) | Mac + Pi + MCU | Command/telemetry framing codec |
| Firmware | `firmware/pibot_arduino/` | Arduino | Command exec, sensors, backstop watchdog, echo test mode |

### 5.3 Key design decisions

- **D1 — Single CLI, importable backends.** `pibot` is a package, not a pile of
  scripts; `pifinder.py` is imported as the discovery backend yet stays runnable
  standalone (don't break the working tool).
- **D2 — The agent is the only transport owner.** Serial ports and I²C buses do not
  tolerate concurrent writers; centralizing the link in `pibotd` removes a whole
  class of race/corruption bugs and is where safety is enforced.
- **D3 — Safety is layered, not located.** E-stop and watchdog exist independently
  in (a) the teleop client, (b) the agent, and (c) the firmware. Wireless transports
  are explicitly **not trusted** to carry the only stop signal.
- **D4 — Transport is an interface, wireless is just a backend.** "Wirelessly if
  possible" is satisfied by `tcp`/`rfcomm`/`ble` backends behind the same
  `Transport` ABC; Bluetooth-RFCOMM notably presents as a serial device, so it
  reuses the serial backend.
- **D5 — Flashing prefers the cable.** The headline reflash path is host USB
  mass-storage (`rpiboot`) because it reimages the soldered-in NVMe without
  disassembly; removable-media and on-Pi clone are the alternates.
- **D6 — Everything reads JSON.** Mirrors `pifinder.py`'s `--json`, so the suite is
  scriptable and testable.

---

## 6. Detailed component design

### 6.1 `pibot` CLI surface

```text
pibot discover [--cidr CIDR] [--all] [--json]          # wraps pifinder
pibot inventory [list|add|rm|alias]                    # ~/.config/pibot/inventory.toml
pibot connect  <target>
pibot run      <target> -- <cmd…> [--json]
pibot push     <target> <src> <dst>
pibot pull     <target> <src> <dst>
pibot keys     install <target> [--identity PATH]
pibot tunnel   <target> <L:host:R>
pibot flash    (--target nvme|sd | --device DEV) --image URI [--sha256 H]
               [--config first-boot.toml] [--dry-run] [--confirm]
pibot provision clone   <target> --to FILE [--shrink]
pibot provision restore <target> --from FILE [--confirm]
pibot eeprom   status|update|config|boot-order [VALUE] [--confirm]
pibot firmware build|flash <sketch> [--target <serial|tcp|…>]
pibot deploy   <target> [--restart] [--rollback] [--dry-run]
pibot agent    status|install|start|stop|logs <target>
pibot teleop   <target> [--gamepad] [--rate HZ]
pibot cmd      <target> <command> [args…]
pibot estop    <target>
pibot play     <target> <sequence.yaml>
pibot monitor  <target> [--json|--csv] [--once] [--interval S]
```

Global flags: `--user`, `--identity`, `--verbose`, `--log-json`, `--dry-run`
(where applicable), `--timeout`.

### 6.2 Configuration

- `~/.config/pibot/config.toml` — defaults (default user, identity, transport,
  rates, thresholds, agent bind/token path).
- `~/.config/pibot/inventory.toml` — known robots (alias, ip, mac, link, last-seen).
- `~/.config/pibot/agent.token` — bearer token, deployed to the Pi.
- `robot/config/transport.toml` — Pi-side: which `Transport` backend + params.

### 6.3 `Transport` abstraction

```text
class Transport(ABC):
    def open() -> None
    def close() -> None
    def send(frame: bytes) -> None          # one encoded protocol frame
    def recv(timeout: float) -> bytes | None # one decoded frame or None
    @property is_open: bool
    @property info: dict                     # backend, endpoint, health

Backends:
  SerialTransport(port, baud)      # USB /dev/ttyACM*, GPIO /dev/serial0, /dev/rfcomm*
  I2CTransport(bus, addr)          # smbus2; register/stream framing
  TcpTransport(host, port)         # Wi-Fi bridge or ESP32 firmware over TCP
  BleTransport(address, char_uuid) # bleak; Nordic-UART-style RX/TX characteristics
```

Selection is config-driven; `rfcomm` (Bluetooth Classic) reuses `SerialTransport`
against `/dev/rfcomm0`. Each backend reports health so the agent can surface
"transport down" telemetry and fail safe.

### 6.4 Pi↔Arduino protocol

Two interoperable encodings sharing one logical message set:

- **Compact framed ASCII (default; Uno-friendly):**
  `>SEQ,CMD,ARG1,ARG2,…*CRC8\n` for commands; `<SEQ,TYPE,FIELDS…*CRC8\n` for
  telemetry; `ACK SEQ` / `NAK SEQ REASON`. CRC8 over the payload; sequence numbers
  for loss/dup detection.
- **JSON lines (ESP32/capable MCUs):** `{"seq":N,"cmd":"drive","v":0.5,"w":0.0}`
  with the same field semantics.

Core message set (extensible): `drive(v,w)`, `motor(id,pwm)`, `servo(id,deg)`,
`stop`/`estop`, `ping`, `set(param,value)`, and telemetry `state`, `battery`,
`current`, `encoder`, `imu`, `range`, `event`. The codec lives in `protocol.py` and
is shared by the agent, the host client, and is mirrored by the firmware parser.

### 6.5 Safety subsystem

- **E-stop** — `POST /estop` and the teleop spacebar set an agent-wide latched stop;
  cleared only by an explicit `resume`. While latched, all actuator commands are
  rejected and a `stop` is asserted to the MCU.
- **Watchdog** — agent halts actuators if `now - last_valid_command > deadman_ms`.
  Firmware runs an independent watchdog (halts if no frame within its own window),
  so a frozen Pi or dropped wireless link still stops the robot.
- **Rate limiting / clamping** — command rates and actuator ranges are clamped to
  configured safe maxima before transmission.

### 6.6 Provisioning internals

- **rpiboot flow** (host): run `rpiboot -d mass-storage-gadget64`; poll for the new
  block device (macOS: diff `diskutil list`; Linux: `lsblk`/udev); confirm it's the
  expected size/model; `diskutil unmountDisk` (macOS) and write to `/dev/rdiskN`.
- **imager flow:** `rpi-imager --cli [--sha256 H] [--disable-verify] <image-uri>
  <device>`; the suite owns hash verification and the first-boot config that the
  CLI does not expose.
- **eeprom flow** (on Pi over SSH): `rpi-eeprom-update -a`,
  `rpi-eeprom-config --edit` for `BOOT_ORDER`; reboot orchestration with health
  re-check.
- **clone flow** (on Pi over SSH): quiesce `pibotd`, copy mounted filesystems into a
  sparse image, shrink, compress, stream back via `pull`.

---

## 7. Data & protocol schemas

- **Telemetry snapshot (`GET /telemetry`, `--json`):**
  `{ ts, pi:{ temp_c, throttled, throttled_flags[], core_volt, cpu_pct, mem_pct,
  load[3], disk:{mount,pct}[], services:{name,state}[] },
  robot:{ battery_v, current_a, encoders[], imu:{…}, ranges[], custom:{…} },
  transport:{ backend, endpoint, up, last_frame_ms }, safety:{ estop, watchdog_ok } }`
- **Throttle decode** — `get_throttled` bitmask expanded to human flags
  (under-voltage, freq-capped, throttled, soft-temp-limit; "currently" vs "since
  boot").
- **Inventory record** — `{ alias, ip, mac, vendor, hostname, user, link:{backend,
  params}, last_seen }`.
- **Motion sequence (`play`)** — YAML list of `{ at: seconds, cmd: …, args: … }`.

---

## 8. Implementation plan & milestones

Each milestone is independently shippable and ends with tests green.

| # | Milestone | Deliverables | Acceptance criteria |
|---|---|---|---|
| **M0** | Foundation | `pibot/` package skeleton, `cli.py` dispatch, `config.py`, inventory, `discover` wrapping `pifinder` | `pibot discover --json` returns the same data as `pifinder.py`; `pibot inventory add` persists; unit tests for config/inventory pass |
| **M1** | Connection & SSH ops | `connect`, `run`, `push`, `pull`, `keys`, `tunnel` | Against the real Pi: passwordless `pibot run pibot -- uptime` works after `keys install`; file round-trips verified by checksum |
| **M2** | Provisioning & flashing | `flash` (rpiboot + imager + removable), first-boot config, `eeprom`, `provision clone/restore` | Reflash onboard NVMe over USB-C end-to-end; `--dry-run` prints exact commands; wrong-disk guard refuses the system disk; EEPROM `boot-order` read/write verified |
| **M3** | Transport + protocol + control | `Transport` backends (**serial + TCP/Wi-Fi**), `protocol.py` codec, `cmd`, `estop`, firmware reference sketch (AVR + ESP32 TCP) + echo mode | `pibot cmd pibot ping` round-trips an ACK through the Arduino over **serial and TCP**; codec unit tests (encode/decode/CRC/seq) pass; e-stop halts a driven motor |
| **M4** | Agent + teleop + telemetry | `pibotd` (HTTP/WS), safety subsystem, telemetry collectors, `teleop`, `monitor`, `agent` mgmt | Live keyboard teleop drives the robot ≤ 50 ms LAN; dropping the socket triggers watchdog stop; `monitor` shows real `vcgencmd`/`psutil` + sensor data |
| **M5** | Deploy + remaining transports | `deploy` (rsync + systemd + venv + rollback), `uart`/`i2c`/`rfcomm`/`ble` backends (TCP already in M3), `play` | `pibot deploy --restart` updates and health-checks the agent; at least one wireless backend drives the robot; rollback restores prior release |
| **M6** | Hardening | Full test suite, docs, `--json` everywhere, structured logging, recovery runbooks | E2E suite green on hardware; CI green using the echo-firmware stand; every destructive op has a tested recovery path |

---

## 9. Technology stack & dependencies

| Concern | Choice | Rationale |
|---|---|---|
| Language (host + agent) | Python ≥ 3.11 | Matches `pifinder.py`; Bookworm/Ubuntu-for-Pi ship 3.11 |
| CLI framework | `argparse` (stdlib) | Consistent with `pifinder.py`; zero-dep core |
| SSH/file ops | system `ssh`/`scp`/`rsync` via subprocess, `paramiko` optional fallback | rsync is the right tool for deploy; avoid heavy deps where the OS tool suffices |
| Agent HTTP/WS | `aiohttp` (or `fastapi`+`uvicorn`) | asyncio-native, WebSocket support for teleop/telemetry push |
| Serial | `pyserial` | De-facto standard; covers USB, GPIO-UART, and `/dev/rfcomm` |
| I²C | `smbus2` | Standard Pi I²C library |
| BLE | `bleak` | Cross-platform asyncio BLE |
| Pi GPIO (if needed) | `gpiozero` + `lgpio` (chip `gpiochip4`) | RPi.GPIO does **not** work on Pi 5 (RP1/`/dev/gpiomem4`); gpiozero+lgpio is the supported path |
| Telemetry | `vcgencmd` (system), `psutil` | Official throttle/temp/voltage source + portable system stats |
| Arduino build | `arduino-cli` | Scriptable firmware build/upload |
| Provisioning (system tools) | `rpiboot`/`usbboot`, `rpi-imager`, `rpi-eeprom-*` | Official Raspberry Pi tooling; verified syntax in §6.6 |
| Tests | `pytest` | Unit/integration/E2E harness |

All third-party deps are pinned in a Pi-side `requirements.txt` installed into a
venv by `deploy`; the host CLI keeps its core dependency-light.

---

## 10. Security considerations

- **SSH** — dedicated `pibot_ed25519` key, never a password in config; `keys install`
  is the only credential-provisioning path.
- **Agent auth** — bearer token required for any non-loopback access; default bind is
  loopback, reached via `pibot tunnel`. Token stored 0600 under `~/.config/pibot/`.
- **Flashing blast radius** — refuse to write to the host system disk; require
  matching size/model or explicit `--device` + `--confirm`; `--dry-run` first.
- **Secure boot** — `flash` supports `rpi-imager --secure-boot-key`; the suite warns
  that signed images are non-bootable on a Pi 5 without secure-boot enabled.
- **Wireless trust** — control over `tcp`/`ble`/`rfcomm` carries the token and is
  rate-limited; the safety watchdog assumes wireless can drop at any instant.
- **Secrets hygiene** — `.gitignore` covers tokens/keys/inventory; NFR-6.

---

## 11. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Logic-level mismatch** (Pi 3.3 V ↔ Arduino 5 V on UART) | Fried GPIO | Spec mandates a level shifter for `uart`; default to USB serial (5 V-safe); document in firmware README |
| **Serial port contention** | Corrupt frames, hangs | Agent is sole transport owner (D2); CLI never opens the port directly when the agent is running |
| **Flashing the wrong disk** | Data loss on the Mac | Size/model confirmation, refuse system disk, `--dry-run`, `--confirm` (NFR-4) |
| **Comms loss during teleop** | Runaway robot | Layered watchdog + firmware backstop fail-safe to stop (D3, FR-4.6) |
| **Wireless latency/jitter** | Sluggish/unsafe motion | Wireless is opt-in; safety never depends on it; clamp rates; surface `last_frame_ms` |
| **Pi 5 bootloader mode quirk** | Flash won't start | Document power-button-hold-on-connect (no jumper on Pi 5) in `flash` help + runbook |
| **EEPROM bad config** | Unbootable Pi | `--confirm` + keep prior config; recovery via SD-card boot or USB-flash recovery image |
| **macOS raw-disk write friction** | Slow/blocked flash | Use `/dev/rdiskN`, `diskutil unmountDisk` first; detect and instruct on permissions |
| **No hardware in CI** | Untestable control path | Arduino echo-firmware stand + loopback serial; clearly a *test* stand, not a production mock |

---

## 12. Testing strategy

- **Unit** — protocol codec (encode/decode/CRC/seq/dup), config/inventory parsing,
  throttle-bitmask decode, device-selection guards, transport backends against fakes.
- **Integration** — against the real Pi over SSH (`run`/`push`/`pull`/`deploy`),
  agent endpoints with a stub transport, `flash --dry-run` command-line assertions.
- **Hardware-in-the-loop (HIL)** — loopback serial and an **Arduino echo sketch**
  that ACKs commands and emits synthetic telemetry, exercising the full
  transport→protocol→agent path without motors.
- **End-to-end (E2E)** — per the project's E2E definition: a **complete user-facing
  workflow through the entire real system, no mocked components**. Concretely:
  `pibot discover` → `pibot teleop` → real WS to a real `pibotd` on the real Pi →
  real `Transport` → real Arduino → an actuator actually moves → motion confirmed via
  real telemetry; and `pibot flash` reflashing the real NVMe and the Pi booting the
  new image. These require physical hardware and are documented as such; the echo
  stand is explicitly labeled an integration aid, **not** an E2E substitute.
- **Regression** — every fixed bug gets a test before closure (project rule).
- **Gate** — no milestone is "done" until its tests pass with zero regressions.

---

## 13. Directory layout

```text
pibot/
├── README.md
├── tools/
│   └── pifinder.py                 # EXISTS — discovery (also backs `pibot discover`)
├── pibot/                          # host CLI package
│   ├── __main__.py · cli.py · config.py · inventory.py · discovery.py
│   ├── connection.py               # ssh/scp/rsync/tunnel/keys
│   ├── provision/                  # rpiboot.py · imager.py · eeprom.py · clone.py · firmware.py
│   ├── control/                    # client.py · teleop.py · sequence.py
│   ├── protocol.py                 # shared command/telemetry codec
│   └── monitor.py
├── agent/                          # on-Pi `pibotd`
│   ├── pibotd.py · safety.py · telemetry.py · protocol.py (shared)
│   └── transport/                  # base.py · serial.py · i2c.py · tcp.py · ble.py
├── firmware/
│   └── pibot_arduino/              # reference sketch: parser · watchdog · sensors · echo mode
├── deploy/
│   └── pibotd.service              # systemd unit template
├── docs/
│   ├── specs/SPEC-1-pibot-control-suite.md
│   └── runbooks/                   # flash, eeprom-recovery, e-stop, first-boot
└── tests/
    ├── unit/ · integration/ · e2e/ · stands/echo_firmware/
```

---

## 14. Decisions log & open items

| ID | Item | Decision / Owner |
|---|---|---|
| DL-1 | Pi↔Arduino link | "All of the above + wireless" → pluggable `Transport`; **default `serial`(USB)**. Final wiring (USB vs UART vs I²C vs which wireless) is a hardware choice — **Owner: Ryan**, confirmed per-deployment via `robot/config/transport.toml`. Spec is link-agnostic, so this does not block implementation. |
| DL-2 | Flashing scope | "All of the above" → host rpiboot+imager, removable media, on-Pi clone, EEPROM. **Decided.** |
| DL-3 | Capability scope | All areas (connection, teleop/motion, telemetry, deploy, flashing). **Decided.** |
| DL-4 | Runtime model | Hybrid: Mac CLI + on-Pi `pibotd`. **Decided.** |
| DL-5 | Agent web stack | `aiohttp` vs `fastapi+uvicorn` — **Owner: implementer at M4**; default `aiohttp` (lighter on a Pi). Non-blocking. |
| DL-6 | Wireless backend priority | **Ratified 2026-06-11:** TCP/Wi-Fi (ESP32 bridge) is **promoted into M3** alongside serial — wireless teleop reachable by M4. RFCOMM/BLE/I²C/UART remain in M5. Reflected in §8 and the milestone plans. |
| DL-7 | Motor driver / firmware specifics | Out of scope (N4); the reference sketch defines the *protocol contract*, not the motor electronics. **Owner: Ryan.** |

---

## 15. Sources

Technical facts and command syntax in this spec were verified against:

- [raspberrypi/usbboot — RPIBOOT provisioning tool](https://github.com/raspberrypi/usbboot) and [mass-storage-gadget64 README](https://github.com/raspberrypi/usbboot/blob/master/mass-storage-gadget64/README.md)
- [rpi-imager(1) manual page](https://man.archlinux.org/man/extra/rpi-imager/rpi-imager.1.en) and [raspberrypi/rpi-imager](https://github.com/raspberrypi/rpi-imager)
- [NVMe SSD boot with the Raspberry Pi 5 — Jeff Geerling](https://www.jeffgeerling.com/blog/2023/nvme-ssd-boot-raspberry-pi-5/) and [The Pi Hut — Flash an NVMe boot drive with Pi 5](https://thepihut.com/blogs/raspberry-pi-tutorials/how-to-flash-an-nvme-boot-drive-with-raspberry-pi-5)
- [raspberrypi/rpi-eeprom — bootloader EEPROM scripts](https://github.com/raspberrypi/rpi-eeprom) and [rpi-eeprom-update](https://github.com/raspberrypi/rpi-eeprom/blob/master/rpi-eeprom-update)
- [Raspberry Pi GPIO best practices white paper](https://pip-assets.raspberrypi.com/categories/685-whitepapers-app-notes/documents/RP-006553-WP/A-history-of-GPIO-usage-on-Raspberry-Pi-devices-and-current-best-practices) and [Tom's Hardware — Control Pi 5 GPIO with Python](https://www.tomshardware.com/how-to/control-raspberry-pi-5-gpio-with-python-3)
- [The Robotics Back-End — Raspberry Pi/Arduino serial communication](https://roboticsbackend.com/raspberry-pi-arduino-serial-communication/) and [PenguinTutor — RPi/Arduino serial over USB](https://www.penguintutor.com/electronics/rpi-arduino)
