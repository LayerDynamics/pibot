# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PiBot is a wheeled robot — a Raspberry Pi 5 "brain" driving an ESP32 (primary,
wireless) or Arduino (wired) motor controller — and this repo is its full software stack.
The product is delivered as three specs (`docs/specs/`), which is the load-bearing mental
model for the whole tree:

- **SPEC-1 — Control Suite** (`pibot/`, `agent/`, `firmware/`): the `pibot` CLI that
  discovers, provisions/flashes, drives, and monitors the robot, plus `pibotd` — the on-Pi
  daemon that owns the robot link. One operator, one robot, one CLI.
- **SPEC-2 — Autonomy Platform** (`pibot/ml/`, `agent/autonomy.py`): the
  vision-language-action (VLA) pipeline — camera → observation → policy → safety-gated
  actuation, plus dataset recording and fine-tuning. Heavy ML deps live behind the `[ml]`
  extra and are installed **only on the robot**.
- **SPEC-3 — Mission Control** (`app/`, `pibot/mc/`): a Tauri desktop app (React + Rust)
  driving a bundled loopback Python control-plane sidecar that talks to robots over the
  Nebula overlay.

Everything is milestone-driven: `docs/plans/` holds per-milestone task plans (M0–M12.x),
and **`bash scripts/check.sh` passing is the definition of done** for every task.

## Architecture: the layered stack

Commands flow top-to-bottom; telemetry flows back up. Each layer is swappable and the
layer below it is mirrored by a no-hardware fake so the whole stack is testable without a
robot.

1. **Firmware** (`firmware/`) — the "muscles". ESP32 is the **primary** controller: joins
   Wi-Fi, drives motors/servos, and serves the protocol over **TCP :3333**. Arduino is the
   wired alternative over USB serial. Firmware enforces its **own** safety (clamp, latched
   e-stop, 300 ms watchdog, ESP32 link-loss stop) **independently of the Pi** — a frozen
   brain or dropped link still halts the robot.
2. **Protocol** (`pibot/protocol/codec.py`) — the Pi↔controller wire format. CRC-8-guarded
   ASCII framing (`>SEQ,NAME,ARG*CC\n`) or JSON framing. Decoder is fuzz-hardened: bad
   frames raise `DecodeError`, never crash. Mirrored in firmware `protocol.h`.
3. **Transport** (`pibot/transport/`) — pluggable byte pipe: `serial`, `tcp` (ESP32),
   `ble`, `rfcomm`, `i2c`, `uart`, plus `loopback`/`responder` fakes for tests. Selected by
   `cfg.transport`.
4. **Control + safety** (`pibot/control/`) — `client` (AgentClient), `teleop`, `sequence`
   (`pibot play`), `oneshot`, and `safety` (clamp / rate-limit / e-stop gate). `echo.py` is
   the host-side firmware mirror used by the echo-stand round-trip tests.
5. **Agent / `pibotd`** (`agent/`) — the on-Pi aiohttp daemon, run as `python -m agent`. It
   is the **sole owner** of the transport. Bearer-token auth on every route except
   `/healthz`. Endpoints: `/health`, `/telemetry` (snapshot + WS push), `/control` (WS
   command frames → safety → ack/nak), `/estop`, `/config`, `/video`, `/arm/telemetry`
   (read-only stepper-arm joint angles + per-joint homed + e-stop + gripper state + FK end-effector
   pose when `[arm-ik]` is installed), `/arm/control`
   (WS motion frames — joints, `grip`/`tool` end-effector, and a Cartesian `move_cartesian`
   pose-via-IK frame when `[arm-ik]` is installed — through the host arm safety gate →
   `ArmManager`, when an arm is configured). Closed-loop
   autonomy (`agent/autonomy.py`) and the camera broker (`agent/video.py`) run **in-process** here.
6. **CLI** (`pibot/cli.py`) — the host-side `pibot` entrypoint. Subcommands span discover /
   inventory / keys / agent / teleop / monitor / firmware / flash / play / estop / arm / deploy.
   Global flags (`--json`/`--verbose`/`--log-json`/`--timeout`) parse before *or* after the
   subcommand.
7. **ML / Autonomy** (`pibot/ml/`) — `camera`, `dataset` (LeRobot format), `episode_logger`,
   `norm_stats`, `transforms`, `openloop`, `closed_loop`, `pibot_environment`. Uses
   `openpi-client` for the VLA policy. Pinned to `numpy<2`; kept out of core so the
   stdlib-light CLI/agent never import it.
8. **Mission Control sidecar** (`pibot/mc/`) — a **loopback-only** (127.0.0.1, never
   public) aiohttp control plane, launched as `python -m pibot.mc --port 0 --token <t>`. It
   prints `PORT=<n>` on stdout so the Rust supervisor can discover the OS-assigned port.
   `routes_*.py` modules cover control, link, video, autonomy, arm, metrics, sessions,
   episodes, finetune, policy_server, ops, inventory, config, record. `robot_link.py` owns the
   single active link and **delegates to `pibot.control.client.AgentClient`** — it never
   re-implements the link.
9. **Tauri desktop app** (`app/`) — React 19 + TypeScript + Zustand + Tailwind v4 + Radix UI
   frontend (`app/src/`), Rust core (`app/src-tauri/src/`). `supervisor.rs` spawns and
   restarts the sidecar with backoff; the **Rust core holds the e-stop failsafe** (caches
   the robot endpoint so e-stop works even if the webview/sidecar is dead). The sidecar is
   bundled as a PyInstaller `externalBin` via `app/scripts/build-sidecar.sh`.

### Safety is the through-line

E-stop and watchdogs are layered and redundant on purpose: the host deadman watchdog, the
firmware's 300 ms watchdog, and the ESP32 link-loss stop are **independent**, so the robot
stops even when the layer above it can't tell it to. E-stop **latches** (preempts all
motion, requires explicit clear). When touching control, transport, agent, or firmware
code, preserve these invariants — see `docs/runbooks/e-stop.md`.

## Commands

### Python (Control Suite + Autonomy)

The host venv is `.venv`. The runtime package is intentionally stdlib-light.

```bash
.venv/bin/pip install -e .            # core CLI + agent
.venv/bin/pip install -e '.[ml]'      # + VLA/camera deps — ON THE ROBOT ONLY (numpy<2)

bash scripts/check.sh                 # FULL GATE = definition of done (see below)

.venv/bin/ruff check .                # lint
.venv/bin/ruff format --check .       # format check (double quotes, line-length 100)
.venv/bin/mypy pibot agent            # strict typing (disallow_untyped_defs)
.venv/bin/pytest                      # tests (coverage-gated at 80% over pibot+agent)
.venv/bin/pytest tests/test_agent_app.py::test_health -q   # single test
```

`scripts/check.sh` runs ruff check + ruff format --check + mypy + pytest-with-coverage, and
**also** runs the desktop app gate when `pnpm`/`cargo` are present. It is what CI runs.

**Test markers** (`pyproject.toml`): the default run excludes `hardware` and `toolchain`
tests so the gate is hermetic with **zero skips**. Run them explicitly:

```bash
.venv/bin/pytest -m hardware          # needs a real Pi via PIBOT_TEST_HOST
.venv/bin/pytest -o addopts="" -m toolchain tests/test_firmware_compiles.py   # needs arduino-cli + cores
```

### Desktop app (Mission Control — `app/`)

Uses **pnpm**. Frontend = Vite/Vitest; backend = Cargo (Tauri 2).

```bash
cd app && pnpm install --frozen-lockfile
pnpm dev          # vite dev server
pnpm test         # vitest run
pnpm typecheck    # tsc --noEmit
pnpm lint         # eslint
pnpm build        # tsc --noEmit && vite build
pnpm tauri build --debug   # build the .app (needed for the E2E harness)

cd app/src-tauri && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test
```

The Arm screen now includes a lazy-loaded URDF twin: the app-served model lives at
`app/public/arm/pibot_arm.urdf`, the scene component is `app/src/screens/arm/ArmTwin.tsx`, and the
URDF parsing / limit-color helpers are in `app/src/screens/arm/armTwinModel.ts`. Keep the twin driven
by the existing `armStore` telemetry polling path; do not add a second telemetry channel for it.

The E2E suite (`app/e2e/`) is **manual / host-marked**, not in CI: it needs a built `.app`
+ WKWebView + a real `pibotd` stand, which the CI container can't provide. Per the
project's E2E honesty rule, do not relabel a Chromium/integration test as E2E. See
`app/e2e/README.md` for the run procedure and the five required release flows.

### Firmware

```bash
pibot firmware build firmware/pibot_esp32 --fqbn esp32:esp32:esp32
pibot firmware flash firmware/pibot_esp32 --fqbn esp32:esp32:esp32 --ota <esp32-ip>
```

**Robot-arm controller (`firmware/pibot_arm_stm32`, Creality 4.2.2 / STM32F103)** — flashed via
**SD card** (no native USB; full procedure in `firmware/pibot_arm_stm32/sd/README.md`, or `swd/` for
the Pi-5 OpenOCD route). Two non-obvious, mandatory requirements:

- **Build the SD image at the `0x7000` bootloader offset AND with float `printf` linked**, or it
  won't boot / joint telemetry comes out empty (newlib-nano omits float printf):

  ```bash
  arduino-cli compile --fqbn STMicroelectronics:stm32:GenF1:pnum=GENERIC_F103RETX \
    --build-property build.flash_offset=0x7000 \
    --build-property "build.flags.ldspecs=--specs=nano.specs -u _printf_float" \
    --clean --export-binaries firmware/pibot_arm_stm32   # -> pibotarm-sd.bin
  ```

  The `0x7000` offset keeps the Creality bootloader intact, so SD re-flashing stays available
  indefinitely (the `0x08000000` SWD build would clobber it).
- **Rename the `.bin` to a UNIQUE name on EVERY flash** (`pibotarm2.bin` → `pibotarm3.bin` → …) and
  keep exactly one `.bin` on the card. The bootloader tracks the last-flashed name and **silently
  skips a matching name**; its `firmware.bin`→`.CUR` rename is unreliable on the 4.2.2, so the fresh
  name is mandatory, not optional. Insert the card at power-on, wait ~15–20 s, then verify over the
  board's USB/CH340 (USART1 @115200) — telemetry must stream real joint values.

### CI (`.github/workflows/ci.yml`)

Three jobs: **gate** (ubuntu, `scripts/check.sh`), **firmware** (ubuntu, arduino-cli
compile of all sketches + host echo-stand round-trip), **desktop** (macOS, frontend +
Rust gate — macOS because Tauri's Rust build needs the platform webview).

## Working in this repo

- **No-hardware development is the default.** Use the `responder`/`loopback` transports and
  `pibot/control/echo.py`; never make the standard test gate depend on real hardware.
- **Keep the `[ml]` boundary intact.** The CLI and `agent` core must never import `pibot.ml`
  / numpy / opencv at module load — those deps exist only on the robot. The same rule covers the arm
  kinematics extra (`[arm-ik]`: ikpy/numpy/scipy): `pibot.arm.geometry` is pure-stdlib XML, and
  `pibot.arm.kinematics` lazy-imports ikpy inside `ForwardKinematics`/`IKSolver` — the model is
  generated from the sizing config (`pibot/arm/geometry/`, FK/IK in `pibot/arm/kinematics.py`).
  `IKSolver.solve` rejects (raises) an unreachable pose or an out-of-limit joint solution rather than
  emitting it — never send an unchecked IK result to the motors (SPEC R5). Cartesian motion reaches
  the stack as `pibot arm move-xyz <target> <x> <y> <z> --seconds <s> [--rx --ry --rz]` (mm / degrees
  at the CLI boundary) and `POST /api/arm/move-cartesian`, both naking cleanly as `"IK unavailable"`
  when `[arm-ik]` / the model isn't installed.
- **The sidecar is loopback-only and the link layer is delegated, not duplicated** — new MC
  features add a `routes_*.py` module and reuse `AgentClient`, they don't open their own
  robot connection.
- Plans in `docs/plans/` are authoritative task lists; runbooks in `docs/runbooks/` are the
  operational source of truth. Specs are `docs/specs/SPEC-{1,2,3}`.
