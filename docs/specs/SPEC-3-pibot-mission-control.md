# SPEC-3 — PiBot Mission Control

| | |
|---|---|
| **Spec ID** | SPEC-3 |
| **Title** | PiBot Mission Control — a Tauri desktop command-and-control app over a bundled Python control-plane sidecar |
| **Status** | Draft |
| **Version** | 1.0 |
| **Author** | Ryan O'Boyle (`durbanpoisonpew@protonmail.com`) + Claude |
| **Created** | 2026-06-12 |
| **Depends on** | [SPEC-1](SPEC-1-pibot-control-suite.md) (M0–M6, shipped — CLI, `pibotd`, transport, safety, telemetry, deploy/flash); [SPEC-2](SPEC-2-pibot-autonomy-platform.md) (M7–M11, software complete — camera, VLA autonomy in-process in `pibotd`, LeRobot data, policy server) |
| **Realizes** | SPEC-1 **non-goal N2** — "a graphical desktop/web app … the agent exposes an API a GUI *could* later use" ([SPEC-1 §2.2](SPEC-1-pibot-control-suite.md)) |
| **Target repo** | `/Users/ryanoboyle/pibot` |
| **Primary host** | MacBook Pro M4 Max (macOS, Apple Silicon) — the same machine that runs the openpi policy server (SPEC-2) |
| **Robot platform** | Raspberry Pi 5 (8 GB) + NVMe + USB camera; ESP32 wireless controller; reached over the Nebula overlay |

> Turn the headless `pibot` CLI + `pibotd` API into a **desktop mission-control app**: a
> Tauri window (React + Radix + Tailwind + Zustand, built with pnpm + Vite) that bundles the
> existing Python `pibot` suite as a **local control-plane sidecar**, streams live telemetry
> and the robot's camera, drives teleop and VLA autonomy through the unchanged on-robot safety
> gate, manages the policy-server brain, reviews demonstration data, and wraps the destructive
> flash/deploy ops behind GUI guards — one operator, one robot, one pane of glass.

---

## 1. Background

### 1.1 Problem Statement
Every PiBot capability exists today only as a **terminal command or a TUI**: `pibot teleop`
to drive, `pibot monitor` for a text telemetry table, `pibot autonomy --run` to start the VLA
loop, `pibot flash`/`deploy`/`firmware` for ops. The operator drives blind — there is **no
live view of the robot's camera** anywhere on the operator side (frames are produced on the
Pi and sent only to the policy server; [`agent/telemetry.py`](../../agent/telemetry.py)'s
snapshot carries no image), telemetry is a momentary text dump with **no history or charts**,
and switching between driving, watching autonomy, reviewing the data you collected, and
reflashing means juggling multiple terminals and remembering flag combinations. SPEC-1
explicitly deferred the GUI (N2) but built the API for it; SPEC-2 added autonomy, a camera,
and a policy brain that an operator now genuinely needs to *see*. This spec builds that GUI:
a single desktop application that makes the whole suite legible and operable, **without
reimplementing or weakening any of the Python control or safety logic underneath it.**

### 1.2 Current State
- **Mac side (shipped):** the stateless `pibot` CLI (Python ≥ 3.11, [`pibot/cli.py`](../../pibot/cli.py), 1048 lines, subcommands `discover`/`inventory`/`run`/`connect`/`push`/`pull`/`keys`/`tunnel`/`flash`/`eeprom`/`provision`/`firmware`/`cmd`/`estop`/`teleop`/`monitor`/`agent`/`deploy`/`play`/`autonomy`); the async [`AgentClient`](../../pibot/control/client.py) (aiohttp HTTP/WS client of `pibotd`); `pibot monitor` (TUI/`--json`/`--csv` over `/telemetry`); config/inventory ([`pibot/config.py`](../../pibot/config.py), `pibot/inventory.py`) under `~/.config/pibot`; the bearer-token file `agent.token`.
- **On-robot (shipped):** `pibotd` (aiohttp) at `agent_bind` (default `127.0.0.1:8787`) exposing `GET /healthz` · `GET /health` · `GET /telemetry` (+ WS push) · `WS /control` · `POST /estop` · `POST/GET/DELETE /autonomy` · `GET/POST /config`, all behind bearer auth + loopback trust ([`agent/app.py`](../../agent/app.py)). The single safety gate (clamp · latched e-stop · 300 ms deadman) is the only path to the motors; closed-loop VLA autonomy now runs **in-process inside `pibotd`** against the remote policy server (commit `d667375`).
- **Policy brain (software complete, SPEC-2):** the openpi `WebsocketPolicyServer` serving π₀.₅ on the M4 Max at `:8000`, launched manually via `scripts/serve_policy.py`.
- **Telemetry shape (shipped):** `assemble_snapshot` → `{ts, pi, robot, transport, safety:{estop}, policy:{connected,last_inference_ms,chunk_age_ms}}` ([`agent/telemetry.py`](../../agent/telemetry.py)).
- **Not built:** any GUI; any operator-facing camera/video path on `pibotd`; any persisted telemetry history; any visual data/episode browser; any desktop packaging. No `app/`, `frontend/`, or `desktop/` directory exists yet.

### 1.3 Target Users
A **single builder-operator** (the author), **one robot**, on **one Mac** (the M4 Max that
also hosts the policy server). No fleet, no multi-tenant, no remote/web users, no shared
deployment. The same person drives, watches autonomy, collects and reviews data, and reflashes
— this app is the cockpit for all of it.

### 1.4 Motivation
Three drivers: **(a) visibility** — autonomy and a camera now exist (SPEC-2) but the operator
cannot see what the robot sees or how the policy link is behaving except as log lines; a VLA
driving a robot you can't watch is operationally unacceptable. **(b) Ergonomics** — the full
suite is powerful but spread across a dozen subcommands and flag combinations; a GUI collapses
"connect → see vitals + video → drive → launch autonomy → review the run → reflash" into one
window. **(c) Operability** — persisted metrics, session recordings, and streamed ops-job logs
turn one-shot terminal output into reviewable history. The API to do all this already exists
(SPEC-1 built it for exactly this); the only missing on-robot piece is an operator video
endpoint, and the rest is a client.

### 1.5 Assumptions
- The desktop app and the openpi **policy server run on the same machine** (the M4 Max), so
  policy-server lifecycle management (FR-PS) is **local subprocess control**, not remote.
  (SPEC-2 keeps the policy host swappable; remote-host control is a post-V1 SSH path — OQ-9.)
- `pibotd` is reachable from the Mac over Nebula (`192.168.100.x`) with a valid bearer token,
  exactly as `pibot teleop`/`monitor` already require.
- The existing Python suite is the **source of truth** for transport, protocol, safety,
  config, inventory, deploy, flash, and the autonomy client — the desktop app reuses it
  verbatim and never re-implements it (Decision D-1, D-6).
- A single USB UVC camera frame source on the Pi can be **shared** by both the in-process
  autonomy loop and a new operator video endpoint via one capture broker (Decision D-8; OQ-2).
- macOS (Apple Silicon) is the only target OS; the app is a **native desktop binary**, not a
  hosted web app.

---

## 2. Requirements

### 2.1 Functional Requirements

Domains (all four committed for V1 — Decision D-4): **Shell/plumbing**, **Live ops**,
**Autonomy**, **Data & models**, **Provisioning/deploy**, plus **Metrics/observability**.

| ID | Priority | Requirement |
|----|----------|-------------|
| **Shell & control plane** | | |
| FR-1 | MUST | The app MUST bundle the existing `pibot` Python suite as a **supervised sidecar process** (the Mission Control host, `pibot.mc`); the Tauri Rust core MUST spawn, health-check, restart-on-crash (with backoff), and cleanly terminate it on app exit. |
| FR-2 | MUST | The sidecar MUST expose a **local control-plane API** (aiohttp HTTP/WS) bound to **loopback only** on an ephemeral port; the webview MUST authenticate to it with a **per-launch bearer token** brokered by the Rust core. No control-plane port may bind a non-loopback interface. |
| FR-3 | MUST | The app MUST manage the **robot inventory** (list/add/remove/alias) and **connect/disconnect** to a robot's `pibotd` over Nebula using the stored agent bearer token, reusing `pibot/inventory.py` + `AgentClient`. |
| FR-4 | MUST | The app MUST surface and edit **configuration** with the **same validation rules** as `pibot/config.py` (unknown-key / wrong-type rejection), and push robot-side settings via `pibotd`'s `GET/POST /config`. |
| **Live ops** | | |
| FR-5 | MUST | The app MUST render a **live telemetry dashboard** of the full snapshot (`pi`, `robot`, `transport`, `safety`, `policy`) streamed over WS at the agent's `telemetry_interval`, with the same threshold alerts as `pibot monitor` (hot SoC, throttle, low battery, transport down, e-stop, stale policy). |
| FR-6 | MUST | The app MUST provide **keyboard teleop** — issue `drive(v, ω)` (and `servo`/`stop`) command frames over `WS /control` through `pibotd`'s safety gate, maintaining command cadence so the host deadman stays fed while driving. |
| FR-7 | MUST | The app MUST provide **gamepad teleop** via the web Gamepad API (analog stick → `drive(v, ω)`), with the same clamping/cadence as keyboard teleop. |
| FR-8 | MUST | The app MUST present an **always-available e-stop** — a persistent on-screen button **and** a global hotkey — that issues `POST /estop` and works **even if the control/telemetry/video sockets are down, and even if the sidecar process itself is down**: the Rust core MUST cache the robot endpoint + agent token at connect time so it can issue `POST /estop` directly without the sidecar. The latched state MUST be visually unmistakable until cleared. |
| FR-9 | MUST | The app MUST display the **robot's live camera** as an MJPEG stream relayed from a new `pibotd` video endpoint; video MUST be best-effort and MUST NOT block or delay control or e-stop. |
| FR-10 | MUST | **`pibotd` MUST gain an operator-facing `WS /video` endpoint** (MJPEG, behind the existing bearer auth) fed by a **single camera-frame broker** shared with the autonomy loop, with configurable resolution/fps and server-side frame throttling. |
| **Autonomy** | | |
| FR-11 | MUST | The app MUST **start/stop closed-loop autonomy** via `pibotd` `POST/DELETE /autonomy`, choosing the task/prompt (the three SPEC-2 behaviors + free-text), the **speed clamp** (`max_speed`), and `control_hz`. |
| FR-12 | MUST | During autonomy the app MUST display **policy-link health** live — `connected`, `last_inference_ms`, `chunk_age_ms` (staleness), inference latency trend — and reflect drop-to-stop when the link stalls. |
| FR-13 | MUST | The app MUST manage the **openpi policy server** lifecycle on the host (start/stop/health-check `serve_policy.py`), show the **loaded checkpoint** and live inference latency, and let the operator **select which checkpoint** to serve. |
| **Data & models** | | |
| FR-14 | MUST | The app MUST **record teleop demonstrations** (the SPEC-2 `autonomy --record` path → obs/action/timestamp) and start/stop recording from the UI, tagged with the task prompt. |
| FR-15 | MUST | The app MUST **browse the LeRobot dataset** — list episodes, show per-episode metadata (task, length, timestamps), and review recorded frames where available. |
| FR-16 | MUST | The app MUST **track fine-tune runs** and which checkpoint is currently served, and trigger **serving a selected checkpoint** (re-launch the policy server against it). |
| FR-17 | SHOULD | The app SHOULD allow **launching a fine-tune run** from the UI and stream its progress/log (training is long and heavy; tracking is MUST, launching is SHOULD). |
| **Provisioning & deploy** | | |
| FR-18 | MUST | The app MUST run the **ops** commands — `flash`, `provision clone/restore`, `firmware build/flash`, `eeprom`, `deploy` — as **async jobs** with **streamed progress and logs** in the UI, reusing the existing `pibot` implementations. |
| FR-19 | MUST | Every **destructive** op (disk/bootloader writes) MUST reproduce SPEC-1's safety contract in the GUI: explicit **`--confirm`-equivalent modal**, the **wrong-disk guard**, and a **`--dry-run` preview** shown before execution. **No GUI path may bypass these guards.** |
| **Metrics & observability** | | |
| FR-20 | MUST | The app MUST **persist telemetry/metrics as a local time-series** and render **historical charts**, with **CSV/JSON export** (the "complete metrics" requirement — Decision D-3). |
| FR-21 | MUST | The app MUST **record each operating session** (telemetry + control/autonomy/ops events) to a replayable, exportable session log (Decision D-3, "live + recording"). |
| FR-22 | SHOULD | The app SHOULD raise **native notifications** on threshold breaches (hot SoC, low battery, e-stop latched, policy stale) when the window is unfocused. |
| **Future / excluded** | | |
| FR-23 | COULD | The app COULD add a **WebRTC** low-latency video track if MJPEG glass-to-glass latency proves inadequate (the `WS /video` abstraction is designed to allow it — FR-10). |
| FR-24 | COULD | The app COULD support **simultaneous multi-robot** dashboards (inventory already holds several; V1 operates **one active robot at a time**). |
| FR-25 | WONT | The app WILL NOT **re-implement** transport, protocol, safety, config, or the autonomy client in TS/Rust — the Python suite is the single source of truth (Decision D-6). |
| FR-26 | WONT | The app WILL NOT run the **VLA model** itself, weaken or bypass the **on-robot safety gate**, or ship as a **browser/mobile/hosted** web app (it is a native macOS desktop binary). |

### 2.2 Non-Functional Requirements

#### Performance
| Metric | Target | Measurement |
|--------|--------|-------------|
| Teleop command latency (keypress/stick → `pibotd` ACK, over Nebula) | p95 ≤ 100 ms (webview→sidecar loopback adds ≤ 5 ms) | client timestamp on send vs ACK receive |
| Telemetry render latency (snapshot received → DOM reflects it) | ≤ 50 ms | perf marks in the renderer |
| Telemetry stream rate | match agent `telemetry_interval` (default 10 Hz) with ≤ 1 % dropped/late frames | sequence-gap count |
| Video | ≥ 10 fps at ≥ 480p over Nebula; glass-to-glass ≤ 400 ms | frame-arrival rate + timestamped frame |
| E-stop dispatch (activate → `POST /estop` sent) | ≤ 50 ms, independent of telemetry/video state | renderer→network mark |
| App cold start (launch → connected dashboard) | ≤ 5 s on the M4 Max | wall-clock |
| Metrics persistence | sustain 10 Hz writes with ≤ 1 % sample loss | store row count vs frames received |
| Memory footprint | ≤ 300 MB idle, ≤ 600 MB under video + autonomy | Activity Monitor / `tauri` metrics |

#### Reliability
| Metric | Target |
|--------|--------|
| Sidecar crash recovery | auto-respawn ≤ 2 s with exponential backoff; UI shows "control plane reconnecting" |
| E-stop reachability | 100 % whenever the **robot link** is up — independent of the sidecar (the Rust core caches the robot endpoint + token at connect) and of the telemetry/video/control sockets |
| Safety-bypass | **0** — no GUI action reaches the motors except through `pibotd`'s gate (test-proven, FR-26) |
| Fail-safe on app/sidecar/link death | robot stops ≤ 300 ms via the **unchanged** `pibotd` host deadman + ESP32 firmware watchdog (inherited from SPEC-1/2) |
| Destructive-op guard | **0** GUI executions of a disk/bootloader write without the modal confirm + wrong-disk guard passing |

#### Security & Compliance
- **Local control plane:** loopback-bind only; per-launch random bearer token brokered by the Rust core (never written to disk in plaintext); strict Tauri **CSP** (no remote origins, no `eval`); Tauri **allowlist** scoped to only the commands the app uses.
- **Robot link:** unchanged — Nebula (cert-based, encrypted) + `pibotd` bearer token (`0600`, gitignored), reused via `AgentClient`.
- **Policy websocket:** optional `api_key` (SPEC-2 OQ-5) honored if set.
- **Secrets:** the M6 security-invariants test is extended to cover the sidecar and any new config — WiFi creds, Nebula keys, `HF_TOKEN`, agent token, and the per-launch token are never committed.
- **Data classification:** demonstration video/state + session recordings + metrics are the operator's private data, stored **locally**, never published.
- **Compliance:** none (personal project). Gemma license applies to π₀ weights for any redistribution (inherited from SPEC-2).

#### Scalability
Single operator, one active robot, one host. Inventory may hold several robots but only one is
driven at a time (FR-24). The only growth axis is the **local metrics/session store**, which is
**retention-bounded** (size cap + age cap — OQ-7). Explicitly **not** a fleet console.

### 2.3 Constraints
- **Frontend stack is user-mandated (Decision D-7):** **Tauri v2** shell; **pnpm** package manager; **Vite** bundler; **React**; **Radix UI** primitives; **Tailwind CSS**; **Zustand** state. No substitutions.
- **C2 shape is A2 (Decision D-1):** a **Python sidecar bundled in the Tauri app** — not a standalone always-on daemon, not a direct-to-`pibotd` TS client.
- **Sidecar reuses `pibot` (≥ 3.11)** and MUST NOT pull the heavy SPEC-2 `[ml]` extra (jax/torch/openpi-client live **on the robot**; the sidecar only *talks to* `pibotd`).
- **Only one `pibotd` addition is permitted:** the `WS /video` endpoint (FR-10). All other robot interactions use the existing API unchanged.
- **macOS / Apple Silicon** is the only supported target.

### 2.4 Explicit Non-Goals
- A standalone Mac daemon or hosted/web/mobile client (FR-26); multi-operator or simultaneous multi-robot control (FR-24/25); re-implementing the Python control/safety stack (FR-25); running the VLA model in the app; replacing the CLI (the app **complements** it — both remain first-class); cross-platform (Windows/Linux) builds; code-signing/notarization for distribution (personal use — OQ-6).

---

## 3. Architecture

### 3.1 System Overview
A **client/sidecar** desktop app. The Tauri Rust core is a thin **shell + supervisor**; the
React webview is the **UI**; the bundled Python **Mission Control host (`pibot.mc`)** is the
**control plane** that aggregates everything and reuses the entire `pibot` suite. The only
network hop the operator's machine makes is the **existing** Nebula link to `pibotd` (plus a
**local** subprocess link to the openpi policy server, which lives on the same Mac).

```text
┌──────────────────────── MacBook Pro M4 Max (macOS) ─────────────────────────────────────┐
│                                                                                          │
│  ┌──────────────── PiBot Mission Control (Tauri v2 app, single process tree) ─────────┐  │
│  │                                                                                     │  │
│  │  React webview  (Vite · pnpm · Radix · Tailwind · Zustand)                          │  │
│  │   Dashboard · Drive(teleop) · Autonomy · Data · Provisioning · Settings            │  │
│  │        │  fetch / WebSocket  →  http://127.0.0.1:<ephemeral>  (per-launch token)    │  │
│  │        ▼                                                                            │  │
│  │  Tauri Rust core  — window · single-instance · global e-stop hotkey ·              │  │
│  │     sidecar SUPERVISOR (spawn/health/restart/kill) · token broker · file dialogs   │  │
│  │        │  spawns + supervises (externalBin)                                         │  │
│  │        ▼                                                                            │  │
│  │  Mission Control host  `pibot.mc`  (Python aiohttp, loopback-only)  ◀── NEW ──      │  │
│  │   • Local control-plane API (HTTP/WS)        • Robot-link mgr  (wraps AgentClient)  │  │
│  │   • Policy-server mgr (local subprocess)     • Ops-job runner (flash/deploy/…)      │  │
│  │   • Metrics recorder → SQLite time-series    • Video relay (pibotd /video → webview)│  │
│  │   • Session recorder → session log           • reuses pibot {config,inventory,…}    │  │
│  └───────────┬──────────────────────────────────────────────┬──────────────────────────┘  │
│              │ local subprocess (manage)                     │ Nebula 192.168.100.x        │
│              ▼                                                │ (bearer token, unchanged)   │
│   openpi WebsocketPolicyServer :8000  (π₀.₅, MPS)            │                              │
└──────────────────────────────────────────────────────────────┼──────────────────────────────┘
                                                                ▼
              ┌──────────────── Raspberry Pi 5 (PiBot, Bookworm) ──────────────────┐
              │  pibotd (aiohttp) — sole transport owner + single safety gate       │
              │   GET /healthz /health · GET+WS /telemetry · WS /control · POST     │
              │   /estop · POST/GET/DELETE /autonomy · GET/POST /config             │
              │   WS /video  ◀── NEW (MJPEG, operator-facing) ──                    │
              │   camera-frame broker ─┬─► in-process autonomy loop (SPEC-2)        │
              │                        └─► /video relay (operator)                  │
              │   safety: clamp · latched e-stop · 300 ms deadman → M3 → ESP32      │
              └────────────────────────────────────────────────────────────────────┘
```

**Why A2 (sidecar), not a standalone daemon:** every Mac-side failure already fails safe —
GUI/sidecar death drops the control WS, `pibotd`'s 300 ms deadman stops the robot; autonomy
runs on the Pi against the policy server, so a dead Mac yields no actions → the robot stops.
A persistent daemon "to keep the link alive" therefore buys nothing the watchdogs don't already
guarantee, while a sidecar reuses 100 % of the Python suite with one lifecycle to manage
(Decision D-1).

### 3.2 Component Design

#### Component: Tauri Rust core (shell + supervisor) — `src-tauri/`
- **Responsibility:** own the native window and lifecycle; **supervise** the Python sidecar (spawn as a Tauri `externalBin`, health-probe, restart with backoff, kill on exit); broker the per-launch loopback token to the webview; register the **global e-stop hotkey**; provide native file dialogs (image/dataset paths); enforce single-instance.
- **Technology:** Tauri v2 (Rust), `tauri-plugin-shell` (sidecar), `tauri-plugin-global-shortcut`, `tauri-plugin-dialog`, `tauri-plugin-single-instance`.
- **Interfaces:** Tauri commands `mc_endpoint()` (returns the local-API `{url, token}`); `cache_robot_endpoint({url, token})` (the sidecar pushes the **robot's** `pibotd` URL + agent token here on connect, so the core holds them independently); `estop_now()` (failsafe `POST /estop` straight to the robot using that cached endpoint — works even if the webview is wedged **or the sidecar is dead**); `sidecar_status()`.
- **Dependencies:** the packaged `pibot.mc` sidecar binary. The cached robot endpoint makes the e-stop failsafe independent of the sidecar's liveness (the one failure mode the failsafe exists for).

#### Component: React webview (UI) — `src/`
- **Responsibility:** render every operator workflow; hold UI state; talk to the sidecar's local API over fetch/WebSocket.
- **Technology:** React + Vite + pnpm; **Radix UI** primitives (Dialog, Tabs, Slider, Toast, DropdownMenu, Tooltip, AlertDialog for destructive confirms); **Tailwind** for styling; **Zustand** stores (`connectionStore`, `telemetryStore`, `videoStore`, `teleopStore`, `autonomyStore`, `policyServerStore`, `dataStore`, `opsStore`, `metricsStore`, `settingsStore`).
- **Screens:** Dashboard (vitals + video + e-stop), Drive (teleop), Autonomy, Data & Models, Provisioning, Settings. Persistent top bar: connection state + **always-visible e-stop**.
- **Dependencies:** the sidecar local API; the Rust `estop_now` command as a failsafe path.

#### Component: Mission Control host — `pibot/mc/` (NEW Python module)
- **Responsibility:** the **control plane**. Serve the loopback HTTP/WS API; hold the robot link; manage the policy server; run ops jobs; record metrics and sessions; relay video. It is the single place the webview talks to, and it **delegates all robot/ops logic to the existing `pibot` suite**.
- **Technology:** aiohttp (same stack as `pibotd`), reusing `pibot.control.client.AgentClient`, `pibot.config`, `pibot.inventory`, `pibot.deploy`, `pibot.provision`, `pibot.monitor.check_thresholds`, and the autonomy CLI paths.
- **Interfaces:** the local control-plane API (§3.4).
- **Dependencies:** `pibot` core (no `[ml]`); a local SQLite file under the app's state dir.
- **Sub-components:**
  - **Robot-link manager** — owns one `AgentClient` per active robot; opens `WS /control`, `WS /telemetry`, `WS /video`; fans telemetry to (a) the webview, (b) the metrics recorder, (c) the session recorder, (d) threshold alerting. **On connect it pushes the resolved robot `pibotd` URL + agent token to the Rust core** (`cache_robot_endpoint`) so the e-stop failsafe survives sidecar death (FR-8).
  - **Policy-server manager** — start/stop/health a local `serve_policy.py` subprocess; track checkpoint + latency; expose serve-checkpoint.
  - **Ops-job runner** — wrap `flash`/`provision`/`firmware`/`eeprom`/`deploy` as cancellable jobs with a streamed log channel and the SPEC-1 confirm/dry-run/wrong-disk guards surfaced as structured steps.
  - **Metrics recorder** — append telemetry samples to the SQLite time-series; serve history queries + export.
  - **Session recorder** — bound a recording (telemetry + events) per session; serve replay + export.
  - **Video relay** — subscribe to `pibotd` `WS /video`, forward MJPEG frames to the webview's `WS /api/video` (decoupled from control; droppable).

#### Component: `pibotd` operator video endpoint — `agent/app.py` + `agent/video.py` (NEW)
- **Responsibility:** expose `WS /video` (MJPEG) for operators, fed by a **single camera-frame broker** that also feeds the autonomy loop — one capture loop, multiple subscribers, so `/video` and autonomy never contend for `/dev/video0`.
- **Technology:** aiohttp WS; JPEG encode (Pillow, already a Pi-side dep) at a server-throttled fps/resolution; behind the existing `auth_middleware`.
- **Interfaces:** `WS /video` → binary/base64 MJPEG frames + a small JSON header (seq, ts, w, h).
- **Dependencies:** the camera module (SPEC-2 `pibot/ml/camera.py`) refactored to publish frames to a broker both consumers subscribe to.

#### Component: Reused — `pibot` suite + `pibotd` + openpi policy server
- **Responsibility:** unchanged. Transport/protocol/safety, config/inventory, deploy/flash/firmware/provision, the `AgentClient`, the in-process autonomy loop, and the policy server are all consumed as-is; the only edits are the additive `WS /video` (FR-10) and the camera-broker refactor it requires.

### 3.3 Data Model
Entities the control plane owns or brokers (★ = persisted locally):

| Entity | Shape / source | Lifecycle |
|--------|----------------|-----------|
| **Robot** | inventory entry `{alias, address, user, transport}` (`pibot/inventory.py`) | CRUD via the app; mirrors `~/.config/pibot` |
| **Connection** | active link to one robot's `pibotd` (`AgentClient` + sockets) | one active at a time; opened on connect, closed on disconnect/exit |
| **TelemetrySample ★** | `{ts, pi, robot, transport, safety:{estop}, policy:{connected,last_inference_ms,chunk_age_ms}}` (`assemble_snapshot`) | streamed live; appended to the SQLite time-series; retention-bounded |
| **SessionRecording ★** | `{id, robot, started, ended, events[], telemetry_ref}` | one per operating session; replayable + exportable |
| **VideoFrame** | MJPEG frame `{seq, ts, w, h, jpeg}` from `WS /video` | ephemeral (not persisted by default; OQ-3 covers opt-in capture) |
| **AutonomySession** | `{prompt, task, max_speed, control_hz, started, policy_link_history[]}` | start/stop via `/autonomy`; policy-link series recorded |
| **Episode / Demonstration** | LeRobot episode `(observation, action, timestamp)` (SPEC-2 `EpisodeLogger`) | recorded via `--record`; browsed/reviewed read-only |
| **FineTuneRun ★** | `{id, dataset, started, status, checkpoint_out, served:bool}` | tracked by the app; the served pointer drives the policy server |
| **PolicyServerState** | `{host, port, pid, checkpoint, state, last_infer_ms}` | live process state managed locally |
| **OpsJob ★** | `{id, kind, args, dry_run, confirmed, status, progress, log[]}` | created per ops action; log streamed; retained for audit |
| **Settings ★** | `pibot/config.py` `Config` fields + GUI prefs (units, theme, hotkeys) | validated on edit; pushed to `pibotd /config` where relevant |

The **SQLite store** lives under the app's macOS state dir (e.g. `~/Library/Application
Support/PiBotMissionControl/` — OQ-7) and holds TelemetrySample, SessionRecording, FineTuneRun,
OpsJob, and Settings tables; demonstration episodes remain in the existing LeRobot dataset on
disk (the app indexes, it does not duplicate them).

### 3.4 API & Interface Design
**Local control-plane API** (sidecar ↔ webview; `127.0.0.1:<ephemeral>`; `Authorization:
Bearer <per-launch token>`; JSON unless noted). Prefix `/api`.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | sidecar liveness + version + connected-robot state |
| GET/POST/DELETE | `/api/robots` | inventory CRUD (→ `pibot/inventory.py`) |
| POST | `/api/connect` `{robot}` · POST `/api/disconnect` | open/close the `AgentClient` link |
| WS | `/api/telemetry` | relayed snapshot stream (also fans to metrics + session recorders) |
| GET | `/api/telemetry/history?from&to&fields` | query the SQLite time-series |
| GET | `/api/telemetry/export?from&to&fmt=csv\|json` | export history |
| WS | `/api/video` | MJPEG relay of `pibotd` `WS /video` (best-effort, droppable) |
| WS | `/api/control` | teleop frames `{cmd:"drive",args:{v,w}}` → `pibotd WS /control` (low-latency, cadence-preserving) |
| POST | `/api/estop` | failsafe e-stop → `pibotd POST /estop` |
| GET/POST/DELETE | `/api/autonomy` | status / start `{prompt,max_speed,control_hz}` / stop |
| GET/POST/DELETE | `/api/policy-server` | status / start `{checkpoint}` / stop the local openpi server |
| GET | `/api/episodes` · GET `/api/episodes/{id}` | list/inspect LeRobot demonstrations |
| POST/DELETE | `/api/record` `{prompt}` | start/stop demonstration recording |
| GET/POST | `/api/finetune` | list / launch (SHOULD, FR-17) fine-tune runs |
| POST | `/api/ops/{flash\|clone\|restore\|firmware\|eeprom\|deploy}` | create an ops job → `{job_id}` |
| GET | `/api/ops/{id}` · WS `/api/ops/{id}/log` | job status / streamed log |
| GET/POST | `/api/config` | read/edit validated config (+ proxy to `pibotd /config`) |
| GET | `/api/sessions` · GET `/api/sessions/{id}` | list/replay session recordings |

**New on-robot endpoint** (`pibotd`): `WS /video` — MJPEG frames behind bearer auth, server
fps/resolution from config (`video_fps`, `video_max_dim`), throttled, fed by the shared camera
broker. The full frame + observation/action JSON contracts are in **Appendix B**.

**Tauri command bridge** (webview ↔ Rust): `mc_endpoint() → {url, token}`, `estop_now()`,
`sidecar_status()`, `pick_path(kind)`. Everything else flows over the local HTTP/WS API so that
streaming (telemetry/video/logs) is first-class.

### 3.5 Data Flow
- **Connect:** webview `POST /api/connect{robot}` → robot-link mgr resolves the inventory address + loads the agent token → opens `AgentClient` (`WS /telemetry`, `WS /control`, `WS /video`) over Nebula → telemetry begins fanning to webview + metrics + session recorders.
- **Teleop:** keydown / gamepad poll → `teleopStore` computes `(v, ω)` → `WS /api/control{drive}` → sidecar relays to `pibotd WS /control` → **safety gate** (clamp · deadman) → M3 → ESP32; ACK/NAK/rejected returns to the UI. Cadence is maintained so the deadman stays fed.
- **E-stop:** button/hotkey → `POST /api/estop`. If the webview is wedged **or the sidecar is dead**, the Rust `estop_now` command issues `pibotd POST /estop` directly using the robot endpoint + token the sidecar cached in the core at connect (`cache_robot_endpoint`) → latch → UI shows latched until cleared. The failsafe therefore does not depend on the sidecar being alive.
- **Live video:** `pibotd` camera broker → `WS /video` → sidecar video relay → `WS /api/video` → `<canvas>`; dropped frames never affect control.
- **Autonomy:** webview `POST /api/autonomy{prompt,max_speed,control_hz}` → `pibotd POST /autonomy` (in-process loop drives through the same safety gate) → policy-link telemetry streams back and is charted live; stop via `DELETE`.
- **Policy server:** webview `POST /api/policy-server{checkpoint}` → policy-server mgr spawns `serve_policy.py` locally → health/latency surfaced; serving a fine-tune checkpoint = stop + respawn against it.
- **Ops:** webview `POST /api/ops/flash{...}` → ops-job runner builds a **dry-run preview**, returns it for a **modal confirm**; on confirm (+ wrong-disk guard pass) it runs the real `pibot flash` and streams the log over `WS /api/ops/{id}/log`.
- **Metrics/sessions:** every telemetry sample is appended to SQLite; a session recording bounds a start→stop window of telemetry + events for replay/export.

### 3.6 Integration Points
- **`pibot` suite (Python)** — reused verbatim by the sidecar (config, inventory, AgentClient, deploy, provision, firmware, monitor thresholds, autonomy paths).
- **`pibotd` (on the Pi)** — existing API + the one new `WS /video` endpoint.
- **openpi policy server** — local subprocess managed by the sidecar; serves π₀.₅ / fine-tunes.
- **LeRobot dataset** — indexed/browsed read-only for the Data screen.
- **Nebula** — the unchanged Mac↔Pi overlay link.
- **macOS** — native window, notifications, global hotkey, file dialogs, app-support state dir.

### 3.7 Security Architecture
- **Local plane:** loopback-only bind; per-launch random bearer token generated by the Rust core, handed to the sidecar via env on spawn and to the webview via `mc_endpoint()`; the token never touches disk. Strict Tauri **CSP** (self only; no remote scripts/eval); Tauri capability allowlist scoped to the few commands used.
- **Robot link:** Nebula + `pibotd` bearer token (`0600`, gitignored), reused through `AgentClient` — unchanged.
- **Policy ws:** optional `api_key` honored if configured (SPEC-2 OQ-5).
- **Destructive ops:** the GUI cannot reach a disk/bootloader write without the dry-run preview, the modal `--confirm`-equivalent, and the wrong-disk guard all passing (FR-19) — enforced in the ops-job runner, not the UI, so the guard cannot be skipped by a UI bug.
- **Secrets hygiene:** the SPEC-1 M6 security-invariants test is extended to the sidecar/app config so no secret (WiFi, Nebula keys, `HF_TOKEN`, agent token, per-launch token) is ever committed.
- **Private data:** demonstrations, session recordings, video captures, and metrics are local-only.

### 3.8 Resilience Design
- **Sidecar:** supervised by the Rust core — health-probed, auto-restarted with backoff, killed on app exit; a crash shows "control plane reconnecting" and the robot **fails safe** (control WS drops → `pibotd` deadman stops it).
- **Robot link drop:** UI banner + the inherited `pibotd` host deadman + ESP32 firmware watchdog stop the robot ≤ 300 ms; the app never needs to "catch" a drop to be safe.
- **E-stop:** always reachable via the dedicated `POST /api/estop` path **and** the Rust `estop_now` failsafe, neither of which depends on the telemetry/video/control sockets being healthy.
- **Video:** strictly best-effort and on its own socket; dropped/slow video never backpressures or blocks control or e-stop (FR-9).
- **Metrics writes:** buffered and backpressure-safe; the store is bounded (retention) so disk pressure cannot wedge the app.
- **Policy server down / Mac busy:** autonomy gets no actions → the robot stops (fail-safe, unchanged from SPEC-2).

### 3.9 Observability
- **The app is the observability surface** — live dashboard, charts, policy-link health, ops-job logs, session replays.
- **Sidecar + Rust logs:** structured logs to the app-support log dir; surfaced in a Settings → Logs view.
- **Metrics:** the SQLite time-series powers historical charts + CSV/JSON export (FR-20).
- **Sessions:** recorded telemetry + events are replayable for post-run review (FR-21).
- **Notifications:** native macOS notifications on threshold breaches when unfocused (FR-22).

### 3.10 Infrastructure & Deployment
- **Frontend build:** `pnpm install` → `pnpm vite` (dev, with a proxy to the sidecar) / `pnpm tauri build` (release) → a macOS `.app`/`.dmg`. **Unsigned/ad-hoc** for personal use (notarization deferred — OQ-6).
- **Sidecar packaging:** `pibot.mc` is built into a standalone binary and shipped as a Tauri **`externalBin`** sidecar (mechanism — PyInstaller one-folder vs a pinned bundled venv vs `uv`-built — decided in P1; OQ-4). The `[ml]` extra is **excluded** (it lives on the robot).
- **Repo layout (new):** `app/` (or `desktop/`) holding `src/` (React), `src-tauri/` (Rust), `package.json`/`pnpm-lock.yaml`/`vite.config.ts`/`tailwind.config.ts`; the new Python module under `pibot/mc/`; the new `agent/video.py`.
- **CI:** extend the SPEC-1 gate — `ruff`/`format`/`mypy`/`pytest` now also cover `pibot/mc` and `agent/video`; add a frontend job (`pnpm lint` + `pnpm typecheck` + `pnpm test` (Vitest) + a `pnpm tauri build` smoke). Hardware/model paths stay deselected as in SPEC-1/2.

---

## 4. Implementation Plan

Delivery is a **single comprehensive V1 release** (Decision D-4): the app ships only when all
four domains work. The phases below are the **internal engineering sequence** toward that one
release — each is a runnable, reviewable checkpoint, not a separate ship.

### 4.1 Build Phases (internal checkpoints → one V1 release)

#### Phase P1 — Skeleton: shell + sidecar + connect + dashboard
- **Goal:** the app launches, supervises the sidecar, connects to a robot, and shows live telemetry.
- **Scope:** Tauri v2 shell (`src-tauri/`) + sidecar supervisor + token broker; `pibot/mc/` aiohttp local API (`/api/health`, `/api/robots`, `/api/connect`, `WS /api/telemetry`); React skeleton (Vite/pnpm/Radix/Tailwind/Zustand) with the Dashboard rendering the snapshot + threshold alerts; sidecar packaging mechanism chosen and wired into `tauri build`.
- **Exit criteria:** `pnpm tauri build` produces a launchable `.app`; the app connects to a real `pibotd` (loopback responder stand-in) and renders streaming telemetry; sidecar crash → auto-restart observed.

#### Phase P2 — Live ops: teleop + e-stop + video
- **Goal:** drive the robot from the GUI with the camera live and an always-on e-stop.
- **Scope:** `agent/video.py` `WS /video` + the camera-frame broker refactor (shared with autonomy); sidecar video relay + `WS /api/video`; keyboard + gamepad teleop over `WS /api/control`; the persistent e-stop button + global hotkey + Rust `estop_now` failsafe; the Drive screen.
- **Exit criteria:** teleop p95 ≤ 100 ms; video ≥ 10 fps / ≤ 400 ms glass-to-glass; e-stop works with telemetry/video sockets forcibly killed; **safety-bypass test** proves no GUI command reaches motors except through the gate.

#### Phase P3 — Autonomy + policy-server management
- **Goal:** launch/watch VLA autonomy and manage the brain.
- **Scope:** Autonomy screen (prompt/task, `max_speed`, `control_hz`; live policy-link charts); `/api/autonomy` wiring; policy-server manager (`/api/policy-server` start/stop/health, checkpoint select, latency).
- **Exit criteria:** start→drive→stop a closed-loop session from the UI; policy-link `chunk_age_ms` staleness reflects drop-to-stop; serving a different checkpoint works.

#### Phase P4 — Data & models + metrics/sessions
- **Goal:** record/review data and persist complete metrics.
- **Scope:** demonstration record start/stop (`/api/record`); LeRobot episode browser + frame review; fine-tune-run tracking (+ optional launch, FR-17); the SQLite metrics time-series + historical charts + CSV/JSON export; session recording + replay.
- **Exit criteria:** record a demonstration and see it in the dataset browser; 10 Hz metrics persist with ≤ 1 % loss; export round-trips; a session replays.

#### Phase P5 — Provisioning/deploy + hardening + release
- **Goal:** the destructive ops in the GUI, then ship V1.
- **Scope:** ops-job runner for `flash`/`clone`/`restore`/`firmware`/`eeprom`/`deploy` with dry-run preview + modal confirm + wrong-disk guard + streamed logs; native notifications; Settings/Logs; full test suite + docs/runbooks; final V1 gate.
- **Exit criteria:** every destructive op requires (and cannot bypass) its guard — test-proven; the full **V1 release gate** below passes.

**V1 release gate (single ship):** all four domains functional; the E2E suite green; safety-bypass and destructive-guard tests pass; performance targets (§2.2) met on the M4 Max; docs + runbook written. Only then does V1 release.

### 4.2 Testing Strategy
- **Unit (frontend, Vitest):** Zustand stores (teleop `(v,ω)` mapping, clamp, cadence; threshold alerting mirroring `pibot/monitor.check_thresholds`; metrics chart selectors); pure render logic.
- **Unit (sidecar, pytest):** local-API handlers against a **fake `AgentClient`**; metrics recorder (samples → SQLite rows → history query → export); ops-job runner state machine incl. the **confirm/dry-run/wrong-disk guard** logic; video-relay framing. Extends the SPEC-1 `ruff`/`mypy`/coverage gate.
- **Unit (Pi, pytest):** `agent/video.py` MJPEG framing + the camera-frame broker fan-out (mocked frames → multiple subscribers; broker shared with a fake autonomy consumer with no `/dev/video0` contention).
- **Integration:** the sidecar local API against a **real `pibotd`** bound to the existing **loopback responder transport** (the SPEC-1 test stand) — connect, teleop, e-stop, autonomy start/stop, telemetry, config — proving the relay path end-to-end **through the real safety gate**. A **safety-bypass** test asserts a GUI-issued motion is clamped/rejected exactly as a teleop command, and a **link-stall** test asserts drop-to-stop.
- **E2E (true full-stack, per the house definition) — macOS-aware harness:** the official `tauri-driver` is **Windows/Linux-only** (Apple ships no WebDriver for embedded WKWebView — verified 2026-06-12), so a macOS E2E MUST drive the **real WKWebView** via an **in-app embedded-WebDriver plugin** (e.g. `tauri-plugin-webdriver` / `tauri-webdriver-automation`, debug build only — mechanism chosen/validated in OQ-11), **not** `tauri-driver` and **not** Playwright-against-Chromium (which would exercise a different engine and a faked backend — that is the integration-mislabeled-as-E2E trap this repo forbids). The harness drives the **built `.app`** (real WKWebView + real Rust core + real **bundled sidecar**) against a **real `pibotd`** on the documented **loopback responder/Arduino-echo stand** (the realistic robot stand-in). Every layer the operator's action touches runs for real — WKWebView React → Rust IPC → local API → sidecar → `AgentClient` → `pibotd` → safety gate → transport → ACK back, with telemetry/video frames rendering in the real DOM. Flows: connect → see telemetry + a video frame; teleop drive → ACK observed; e-stop latches (incl. the **sidecar-killed** failsafe path) and is visually unmistakable; autonomy start→stop with a fake policy; a destructive op blocked without confirm and executed (against a sandbox image/disk) with it. **No layer mocked** beyond the documented hardware stand-in. If a robust macOS embedded-WebDriver mechanism cannot be stood up (OQ-11), the spec will **honestly downgrade** these to host-marked **manual** E2E runs rather than relabel a Chromium/integration test as E2E. (Lower tiers above are labeled integration/unit, never E2E.)
- **HIL / host-marked (manual):** the real app against the real Pi over Nebula with the real camera and the real openpi server — deselected by default like SPEC-1/2 `hardware`/`toolchain` tests.

### 4.3 Rollout Strategy
Internal phase-gating (P1→P5); the app is dogfooded by the author at each checkpoint but
**released once** as V1 when the release gate passes. First real-robot runs reuse the SPEC-2
posture: tethered/low-speed, e-stop in hand, reduced clamp. Rollback = keep using the CLI
(it remains fully functional and is never removed) and/or revert the app build; the `WS /video`
addition is additive and behind auth, so it can't regress existing `pibotd` behavior.

### 4.4 Operational Readiness
Before relying on the app for live driving/autonomy: the safety-bypass and destructive-guard
tests pass; e-stop verified with telemetry/video sockets killed; sidecar crash-restart verified;
video confirmed not to backpressure control; metrics store retention bound configured; the
**autonomy bring-up** and **mission-control** runbooks written. The CLI remains the fallback for
anything the GUI doesn't yet cover.

---

## 5. Milestones

Single V1 milestone (**M12**), delivered as internal phases that all roll up into one release
gate (Decision D-4).

| Milestone | Phase | Goal | Exit Criteria | Owner |
|-----------|-------|------|---------------|-------|
| **M12.1** | P1 | Shell + sidecar + connect + dashboard | launchable `.app`; live telemetry from real `pibotd`; sidecar auto-restart | Ryan |
| **M12.2** | P2 | Teleop + e-stop + video | teleop p95 ≤ 100 ms; video ≥ 10 fps; e-stop survives socket loss; safety-bypass test passes | Ryan |
| **M12.3** | P3 | Autonomy + policy-server mgmt | UI start/stop closed-loop; policy-link charts; checkpoint serve works | Ryan |
| **M12.4** | P4 | Data & models + metrics/sessions | demonstrate record→browse; 10 Hz metrics persist; export + replay work | Ryan |
| **M12.5** | P5 | Provisioning + hardening + **V1 release** | destructive guards unbypassable (test-proven); E2E green; perf targets met; **V1 ships** | Ryan |

### Dependency Graph
```text
SPEC-1 (M0–M6, done) ─┐
SPEC-2 (M7–M11, done) ─┴─►  M12.1 ─► M12.2 ─► M12.3 ─► M12.4 ─► M12.5
                            shell    live     auto +   data +   ops +
                            +tlm     ops      policy   metrics  RELEASE
                                     (NEW pibotd /video at M12.2)
                            └──────────── one V1 release at M12.5 ───────────┘
```

---

## 6. Success Criteria

### 6.1 Launch Metrics
| Metric | Target | Measurement Method |
|--------|--------|--------------------|
| Domains shipped in V1 | 4/4 (live ops, autonomy, data, provisioning) + metrics | release-gate checklist |
| Teleop command latency | p95 ≤ 100 ms over Nebula | in-app latency meter |
| Video | ≥ 10 fps, ≤ 400 ms glass-to-glass | frame-rate + timestamped frame |
| E-stop reachability under socket loss | 100 % | fault-injection E2E |
| Safety-bypass incidents | 0 | safety-bypass test + audit of command paths |
| Destructive-op guard bypasses | 0 | destructive-guard E2E |
| Metrics sample loss at 10 Hz | ≤ 1 % | store rows vs frames received |
| App cold start | ≤ 5 s | wall-clock |

### 6.2 Ongoing Monitoring
The app monitors itself: dashboard vitals + alerts, policy-link health, ops-job logs, metrics
charts, session replays, sidecar/Rust logs in Settings. Review cadence: per-session (one
operator, one robot).

### 6.3 Remediation Triggers
- Any failure of the **safety-bypass** or **e-stop-under-socket-loss** test → **halt app work** on driving paths; fix before anything else.
- Any destructive op executing without its guard → halt provisioning work; fix the ops-job runner.
- Video backpressuring control (teleop latency regression when video is on) → throttle/decouple video; never let video share control's fate.
- Sidecar failing to auto-restart, or leaking processes on exit → fix supervision before release.

---

## 7. Risks

| ID | Risk | Impact | Likelihood | Mitigation | Contingency |
|----|------|--------|-----------|------------|-------------|
| R-1 | **Sidecar packaging** (bundling aiohttp + `pibot` as a Tauri `externalBin`) is fragile across macOS/Python | High | Medium | Decide the mechanism in P1; CI `tauri build` smoke; pin the interpreter | Ship a pinned bundled venv instead of a frozen binary |
| R-2 | **Camera contention** between `WS /video` and the autonomy loop on `/dev/video0` | High | Medium | Single capture **broker**, multiple subscribers (D-8); one capture loop only | Disable `/video` while autonomy holds the camera; snapshot mode |
| R-3 | **Video bandwidth over Nebula** degrades control latency / risks the deadman | High (safety-adjacent) | Medium | Server-side fps/resolution caps; video on its own socket; never block control (FR-9, §3.8) | Drop to snapshot-only; lower `video_fps`/`video_max_dim` |
| R-4 | **GUI bypassing** a safety/confirm guard (motion or destructive op) | Critical | Low | Guards enforced in the sidecar/ops-runner, not the UI; safety-bypass + destructive-guard tests are release-blocking (FR-19, FR-26) | Block release until proven; CLI remains the trusted path |
| R-5 | **Local token / loopback exposure** (other local processes reaching the control plane) | Medium | Low | Loopback bind + per-launch token + strict CSP + scoped Tauri allowlist | Rotate token per launch; bind to a unix socket if needed |
| R-6 | **Scope** — one big V1 across 4 domains + video + policy mgmt is long to first ship | Medium | High | Internal phasing keeps every checkpoint runnable/dogfoodable; CLI covers gaps meanwhile | Cut COULDs (FR-23/24) and SHOULD (FR-17) to hit the gate |
| R-7 | **Tauri v2 + Python sidecar lifecycle** on macOS (zombies, signal handling, single-instance) | Medium | Medium | Rust supervisor owns spawn/kill; single-instance plugin; cleanup-on-exit; tests | Wrap the sidecar in a process group; reap on `SIGCHLD` |
| R-8 | **Metrics store growth** unbounded | Medium | Medium | Size + age retention caps (OQ-7); buffered, backpressure-safe writes | Auto-prune oldest; expose a "clear history" action |
| R-9 | **Tauri webview perf** for live video + charts at rate (canvas/chart jank) | Medium | Medium | `<canvas>` MJPEG draw; downsample charts; `requestAnimationFrame` budget | Lower render rate; virtualize history charts |
| R-10 | **`pibotd` `/video` regressing** existing agent behavior | Medium | Low | Additive endpoint behind existing auth; the broker refactor is unit-tested against autonomy | Feature-flag `/video`; revert is isolated |

---

## 8. Open Questions

| # | Question | Owner | Due |
|---|----------|-------|-----|
| OQ-1 | Default video **resolution/fps** and the Nebula **bandwidth budget** (measure under teleop + autonomy) | Ryan | P2 |
| OQ-2 | Camera-broker concurrency — does the chosen UVC/capture path cleanly support one loop + N subscribers, or must `/video` yield while autonomy runs? | Ryan | P2 |
| OQ-3 | Should the app **capture/persist video** (per-session clips) or stay live-only (frames ephemeral)? | Ryan | P4 |
| OQ-4 | **Sidecar packaging** mechanism — PyInstaller one-folder vs pinned bundled venv vs `uv` | Ryan | P1 |
| OQ-5 | Should the GUI **launch fine-tune runs** (FR-17) or track-only in V1 (training is long/heavy)? | Ryan | P4 |
| OQ-6 | **Code-signing/notarization** — needed for personal use, or ad-hoc/unsigned is fine? | Ryan | P5 |
| OQ-7 | **State dir** location + **retention** policy (size/age caps) for the SQLite metrics/session store | Ryan | P1 |
| OQ-8 | Teleop transport — confirm `WS /api/control` (cadence/deadman) over per-keypress POST | Ryan | P2 |
| OQ-9 | **Remote policy host** — when the brain moves off the M4 Max (SPEC-2 FR-14), how does the app manage it (SSH/launchd)? | Ryan | post-V1 |
| OQ-10 | Repo home for the desktop app — `app/` vs `desktop/`; monorepo with the Python suite vs a sub-package | Ryan | P1 |
| OQ-11 | **macOS automated-E2E mechanism** — pick/validate an embedded-WebDriver plugin for the WKWebView shell (`tauri-plugin-webdriver` vs `tauri-webdriver-automation`); if none proves robust, scope E2E as host-marked manual runs (the official `tauri-driver` does not support macOS) | Ryan | P2 |

---

## Appendices

### Appendix A — Glossary
- **Mission Control host (`pibot.mc`)** — the new Python aiohttp **sidecar** that is the desktop app's control plane; reuses the `pibot` suite and exposes a loopback HTTP/WS API to the webview.
- **Sidecar (Tauri `externalBin`)** — an external binary the Tauri app spawns and supervises; here, the packaged `pibot.mc`.
- **A2 (Python sidecar)** — the chosen C2 shape: the Python suite bundled inside the Tauri app, vs a standalone daemon (B) or a re-implemented TS client (A1).
- **Control plane** — the layer that owns connections and aggregates state (the sidecar), distinct from the UI (webview) and the shell (Rust core).
- **`pibotd`** — the on-robot aiohttp agent (SPEC-1 M4); the sole transport owner and safety gate.
- **`AgentClient`** — the existing async HTTP/WS client of `pibotd` (`pibot/control/client.py`), reused by the sidecar.
- **MJPEG-over-WS** — the chosen operator video transport: JPEG frames pushed over a WebSocket.
- **Camera-frame broker** — one capture loop on the Pi publishing frames to multiple subscribers (autonomy + `/video`), avoiding `/dev/video0` contention.
- **Safety gate / deadman / firmware watchdog** — the unchanged layered fail-safe (clamp · latched e-stop · 300 ms host deadman · independent ESP32 watchdog).
- **Policy server** — the openpi `WebsocketPolicyServer` serving π₀.₅ on the M4 Max (SPEC-2), managed locally by the sidecar.
- **Telemetry snapshot** — `{ts, pi, robot, transport, safety, policy}` from `assemble_snapshot` (`agent/telemetry.py`).

### Appendix B — Interface Contracts

```jsonc
// Local control-plane: teleop command (webview -> sidecar -> pibotd WS /control)
{ "cmd": "drive", "args": { "v": 0.4, "w": -0.2 } }   // also: servo{id,deg}, stop, ping
// reply (pibotd -> sidecar -> webview)
{ "ack": true, "seq": 12 }                            // or { "nak": "<reason>" } / { "rejected": "estop" }

// Local control-plane: telemetry stream frame (sidecar -> webview)  [= pibotd snapshot]
{
  "ts": 1718200000.12,
  "pi":     { "temp_c": 61.2, "throttled": { "currently": [] }, "load": [..], "mem": {..} },
  "robot":  { "battery": { "volts": 12.1 }, /* latest decoded MCU frames */ },
  "transport": { "open": true, "kind": "tcp" },
  "safety": { "estop": false },
  "policy": { "connected": true, "last_inference_ms": 760.0, "chunk_age_ms": 45.0 }
}

// NEW pibotd WS /video frame (operator video; pibotd -> sidecar -> webview)
{ "seq": 901, "ts": 1718200000.20, "w": 640, "h": 480, "fmt": "jpeg" }   // header
// ...followed by the binary JPEG payload (one header + one binary frame per tick)

// Autonomy start (webview -> sidecar -> pibotd POST /autonomy)
{ "prompt": "drive to the red ball", "max_speed": 0.3, "control_hz": 20 }

// Ops job create (webview -> sidecar)  -> returns { "job_id": "..." }; log over WS /api/ops/{id}/log
{ "kind": "flash", "args": { "image": "...", "disk": "/dev/diskN" }, "dry_run": true }
```

### Appendix C — Decision Log
| # | Decision | Rationale | Source |
|---|----------|-----------|--------|
| D-1 | **C2 shape = A2** (Python sidecar bundled in the Tauri app) | Reuses 100 % of the `pibot` suite; the "daemon for link survival" rationale is void (watchdogs already fail safe); fewest moving parts | discovery 2026-06-12 |
| D-2 | **Live video = MJPEG over WebSocket** | Reuses `pibotd`'s aiohttp WS; robust over Nebula; right-sized for one operator; minimal new Pi deps | discovery 2026-06-12 |
| D-3 | **Metrics = persisted history + session recording** ("one and two") | "Complete telemetry and metrics" → live + historical charts/export + replayable sessions | discovery 2026-06-12 |
| D-4 | **One comprehensive V1** across all four domains | Operator wants the whole cockpit at once; internal phasing sequences the build | discovery 2026-06-12 |
| D-5 | **C2 manages the policy server** (local subprocess on the M4 Max) | Full brain lifecycle from the GUI; the policy host *is* the app host in V1 | discovery 2026-06-12 |
| D-6 | **Sidecar reuses `pibot`; no re-implementation; no `[ml]` extra** | Single source of truth for control/safety; `[ml]` lives on the robot | global rule + SPEC-2 |
| D-7 | **Stack = Tauri v2 · pnpm · Vite · React · Radix · Tailwind · Zustand** | User-mandated | request 2026-06-12 |
| D-8 | **Single camera-frame broker** shared by autonomy + `/video` | Avoids `/dev/video0` contention; one capture loop, many subscribers | design 2026-06-12 |
| D-9 | **The CLI is complemented, not replaced** | The CLI stays the trusted fallback and scripting surface | SPEC-1 + global rule |

### Appendix D — Runbooks (pointers)
- Robot link → [docs/runbooks/nebula-overlay.md](../runbooks/nebula-overlay.md).
- e-stop / fail-safe → [docs/runbooks/e-stop.md](../runbooks/e-stop.md).
- Autonomy bring-up / data / fine-tune-and-serve → [autonomy-bringup](../runbooks/autonomy-bringup.md) · [data-collection](../runbooks/data-collection.md) · [finetune-and-serve](../runbooks/finetune-and-serve.md).
- *To write (P5):* **mission-control bring-up** (install/launch the app, supervise the sidecar, manage the policy server, GUI-wrapped flash/deploy with the confirm/wrong-disk guards).

### Appendix E — Traceability (requirement → component → phase)
| Requirement | Primary component(s) | Phase |
|-------------|----------------------|-------|
| FR-1, FR-2 (shell/sidecar/token) | Rust core; `pibot.mc` | P1 |
| FR-3, FR-4 (inventory/config) | `pibot.mc` (reuses inventory/config) | P1 |
| FR-5 (telemetry dashboard) | `pibot.mc` relay; webview Dashboard | P1 |
| FR-6, FR-7 (keyboard/gamepad teleop) | webview teleopStore; `WS /api/control` | P2 |
| FR-8 (always-on e-stop) | Rust `estop_now`; `POST /api/estop` | P2 |
| FR-9, FR-10 (video + `pibotd WS /video`) | `agent/video.py` broker; sidecar video relay | P2 |
| FR-11, FR-12 (autonomy + policy-link) | `pibot.mc` `/api/autonomy`; webview Autonomy | P3 |
| FR-13, FR-16, FR-17 (policy server / checkpoints / fine-tune) | policy-server mgr | P3 / P4 |
| FR-14, FR-15 (record/browse demonstrations) | `pibot.mc` `/api/record`, `/api/episodes`; webview Data | P4 |
| FR-20, FR-21 (metrics history + sessions) | metrics + session recorders (SQLite) | P4 |
| FR-18, FR-19 (ops + destructive guards) | ops-job runner; webview Provisioning | P5 |
| FR-22 (notifications) | Rust core / webview | P5 |
| FR-23, FR-24 (WebRTC, multi-robot) | (post-V1, design-allowed) | — |
| FR-25, FR-26 (non-goals: no re-impl / no model / native-only) | architecture-wide invariants | all |
