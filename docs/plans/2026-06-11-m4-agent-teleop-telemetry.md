# Plan — M4: Agent, Teleop & Telemetry

| | |
|---|---|
| **Spec** | [SPEC-1](../specs/SPEC-1-pibot-control-suite.md) §4.1 FR-4 (teleop), FR-5, FR-6 |
| **Milestone** | M4 |
| **Depends on** | M3 |
| **Branch** | `m4-agent-teleop-telemetry` |
| **Date** | 2026-06-11 |
| **Status** | Not started |

> Conventions per the
> [roadmap](2026-06-11-pibot-control-suite-roadmap.md#shared-conventions-apply-to-every-task-in-every-milestone).
> **Safety rule is load-bearing here:** the agent is the sole transport owner and the
> central enforcer of e-stop + deadman watchdog; every teleop test must prove the robot
> stops when comms drop.

## Goal
Bring the robot to life under real-time control: the on-Pi `pibotd` agent (HTTP/WS),
its safety subsystem, telemetry collection from both the Pi and the Arduino, and the
Mac-side `teleop` and `monitor` clients.

## In scope
`pibotd` (aiohttp HTTP+WS), safety subsystem (latched e-stop, deadman watchdog, rate
limit), telemetry collectors (vcgencmd, psutil, systemd, MCU), `pibot teleop`, `pibot
monitor`, `pibot agent` management.

## Out of scope
`deploy`/systemd install (M5 — for M4, run the agent manually over SSH/tunnel), the
remaining wireless backends (M5).

## Prerequisites
- M3 (codec, serial + TCP transports, safety primitives).
- A reachable Pi; the agent runs on the Pi, reached from the Mac via `pibot tunnel`
  (M1) or LAN+token.

## Tasks

### T4.1 — `pibotd` skeleton + auth
- **Files:** `agent/pibotd.py`, `agent/app.py`, `agent/auth.py`
- **Test first:** `tests/test_agent_app.py` (aiohttp test client) — `GET /health` →
  200 with version/uptime; non-loopback request without a valid bearer token → 401;
  loopback allowed; config + token loaded from `~/.config/pibot/`.
- **Implement:** aiohttp app, loopback bind default, bearer-token middleware, `/health`,
  graceful startup/shutdown owning the transport handle.
- **Done when:** app + auth tests green.

### T4.2 — Safety subsystem (agent-central)
- **Files:** `agent/safety.py` (builds on `pibot/control/safety.py`)
- **Test first:** `tests/test_agent_safety.py` (injected clock) — latched e-stop
  rejects all motion until `resume`; deadman watchdog halts actuators when `now -
  last_valid_cmd > deadman_ms`; rate limiter drops/clamps over-rate commands; on any
  trip, a `stop` frame is asserted to the (fake) transport.
- **Implement:** the agent-side safety state machine wrapping M3 primitives, wired to
  emit stop frames.
- **Done when:** every trip path covered with a fake clock + fake transport.

### T4.3 — Transport ownership + command queue
- **Files:** `agent/control.py`
- **Test first:** `tests/test_agent_control.py` — a single serialized command queue;
  concurrent `WS /control` producers never interleave frames on the transport; e-stop
  preempts the queue; ACK/NAK from the codec routed back to the sender.
- **Implement:** async single-owner transport loop + priority queue (e-stop highest).
- **Done when:** serialization + preemption + ack-routing tests green.

### T4.4 — Telemetry collectors (parsers exhaustively TDD)
- **Files:** `agent/telemetry.py`
- **Test first:** `tests/test_telemetry.py` — parse `vcgencmd measure_temp`
  (`temp=NN.N'C`), `vcgencmd get_throttled` (**bitmask → human flags**, "currently"
  vs "since boot"), `vcgencmd measure_volts core`; psutil cpu/mem/load/disk mapping;
  `systemctl is-active` states; MCU telemetry frames decoded via the M3 codec into the
  snapshot schema (SPEC-1 §7). Use captured fixtures (no live `vcgencmd` in unit tests).
- **Implement:** collectors + the throttle-bitmask decoder + snapshot assembler.
- **Done when:** every parser/decoder branch covered against fixtures.

### T4.5 — Agent endpoints (REST + WS)
- **Files:** extend `agent/app.py` with routes
- **Test first:** `tests/test_agent_endpoints.py` (aiohttp WS test client) — `GET
  /telemetry` snapshot; `WS /telemetry` pushes periodic snapshots; `WS /control`
  accepts command frames, applies safety, returns ack/nak; `POST /estop` latches;
  `GET/POST /config`.
- **Implement:** the endpoints wired to T4.2–T4.4.
- **Done when:** REST + WS endpoint tests green.

### T4.6 — `pibot teleop` client
- **Files:** `pibot/control/teleop.py`, `pibot/control/client.py`
- **Test first:** `tests/test_teleop.py` — key→command mapping (arrows→velocity,
  keys→servo) at a fixed rate (default 20 Hz); **spacebar → e-stop**; **socket drop →
  client stops sending and the agent watchdog stops the robot** (assert against a fake
  agent); gamepad mapping (optional, `evdev`/`pygame`) behind a fake device.
- **Implement:** WS client + input loop + TUI state view; rate pacing; e-stop binding.
- **Done when:** mapping + e-stop + drop-safety tests green.

### T4.7 — `pibot monitor`
- **Files:** `pibot/monitor.py`
- **Test first:** `tests/test_monitor.py` — renders a snapshot to TUI lines;
  `--json`/`--csv`/`--once` modes; **threshold alerts** (temp≥limit, throttled,
  battery low, transport/agent down) set non-zero exit codes; `--interval` paces polls.
- **Implement:** monitor client (snapshot or stream) + threshold engine + renderers.
- **Done when:** rendering + threshold + mode tests green.

### T4.8 — `pibot agent status|install|start|stop|logs`
- **Files:** `pibot/agent_ctl.py`
- **Test first:** `tests/test_agent_ctl.py` — builds the right on-Pi commands (run the
  agent in a venv, query `/health`, fetch `journalctl`/log tail); `install` here is the
  manual/foreground form (systemd unit lands in M5).
- **Implement:** agent lifecycle helpers over M1 SSH.
- **Done when:** command-construction tests green.

### T4.9 — Integration + E2E (hardware-marked)
- **Files:** `tests/integration/test_agent_live.py`, `tests/e2e/test_teleop_e2e.py`
- **Test:** integration — agent up on the Pi, `/telemetry` returns **real**
  `vcgencmd`/`psutil` values; E2E — `pibot teleop` over a real WS to the real agent
  drives a real actuator and motion is confirmed via real telemetry; dropping the
  socket stops the robot within the watchdog window.
- **Done when:** integration green vs the Pi; E2E recorded on hardware; cleanly skipped
  without `PIBOT_TEST_HOST`.

## Milestone acceptance criteria (SPEC-1 §8 M4)
- Live keyboard teleop drives the robot ≤ 50 ms over LAN/USB.
- Dropping the control socket triggers a watchdog stop.
- `monitor` shows real `vcgencmd`/`psutil` + sensor data.
- All gates green.

## Risks
- **Crashed client/agent leaving actuators energized** → layered watchdog (agent +
  firmware backstop from M3); E2E asserts fail-safe.
- **WS latency under load** → fixed-rate sender, snapshot coalescing; measure in E2E.
- **vcgencmd output drift across OS images** → parsers fixture-driven and tolerant;
  unknown fields surfaced, not crashed.

## Definition of done
All gates pass; acceptance met; real-hardware teleop + telemetry demonstrated; drop-to-
stop proven; branch ready to commit (ask first).
