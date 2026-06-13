# Plan — M12.2: Teleop + E-stop + Video

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. Note adjacent issues as TODOs; do NOT fix them.

**Goal:** Drive the robot from the GUI (keyboard + gamepad) with the camera live and an always-available e-stop that works even if the sidecar is dead — proven by release-blocking safety tests.
**Architecture:** A new `pibotd WS /video` (MJPEG) fed by a single camera-frame **broker** shared with the autonomy loop; the sidecar relays video + control between the webview and `pibotd`; the Tauri Rust core holds a cached robot endpoint so e-stop survives sidecar loss. All motion still passes the unchanged `pibotd` safety gate.
**Tech Stack:** aiohttp WS (Pi + sidecar), Pillow (JPEG), React/Zustand, web Gamepad API, Tauri global-shortcut + Rust HTTP client (`reqwest`).
**Practices:** TDD + typed-first + contract-first.
**Required skills:** none.

| | |
|---|---|
| **Spec** | [SPEC-3](../specs/SPEC-3-pibot-mission-control.md) FR-6…FR-10, FR-26; §3.2 (video), §3.5, §3.8; §4.1 P2; §5 M12.2 |
| **Phase** | P2 (live ops) |
| **Depends on** | M12.1 (shell + sidecar + telemetry) |
| **Branch** | `m12-2-teleop-estop-video` |
| **Date** | 2026-06-12 |
| **Status** | ✅ Shipped — all T12.2.1–T12.2.9 software complete; Python 683 passed, frontend 57 passed, Rust 9 passed; safety-bypass + e-stop-under-loss regressions green |

## In scope
The `pibotd` camera-frame broker refactor + `WS /video`; the sidecar video relay + control
relay; keyboard + gamepad teleop; the always-on e-stop (button + global hotkey + Rust failsafe
on the cached endpoint); the live video canvas; the **safety-bypass** and **e-stop-under-loss**
release-blocking regressions.

## Out of scope
Autonomy/policy server (M12.3); data/metrics (M12.4); provisioning (M12.5); WebRTC (FR-23, COULD,
post-V1 — the `/video` abstraction is kept WebRTC-ready but no track is built here).

## Prerequisites
- M12.1 done (connect + telemetry relay + the `on_connect(url, token)` seam).
- A `pibotd` with the SPEC-2 camera module (`pibot/ml/camera.py`) reachable (real Pi for HIL; a fake frame source for unit tests).

## Contracts (define first — contract-first)
```jsonc
// NEW pibotd WS /video frame (SPEC-3 Appendix B): one JSON header then one binary JPEG per tick.
{ "seq": 901, "ts": 1718200000.20, "w": 640, "h": 480, "fmt": "jpeg" }   // + binary payload
```
```python
# agent/video.py — the broker + endpoint config (typed-first).
class CameraBroker:                 # one capture loop, N subscribers; no 2nd /dev/video0 open
    def subscribe(self) -> "asyncio.Queue[Frame]": ...
    def unsubscribe(self, q) -> None: ...
# config additions (pibot/config.py + agent autonomy_config): video_fps: int = 10, video_max_dim: int = 640
```

## Tasks

### T12.2.1 — `pibotd` camera-frame broker (single capture loop, N subscribers)
- **Files:** create `agent/video.py` (`CameraBroker`, `Frame`); modify `agent/autonomy.py` (consume frames via `broker.subscribe()` instead of opening the camera directly); test `tests/test_camera_broker.py`; touch `tests/test_autonomy_agent.py` (unchanged behavior).
- **Step 1 — failing test:** one mocked capture source fans out to **two** subscribers, each receiving every frame; only **one** capture handle is opened (assert the source is constructed once); unsubscribing stops delivery; the autonomy consumer still receives frames.
- **Step 2 — run:** `pytest tests/test_camera_broker.py` → Expected: FAIL.
- **Step 3 — implement:** `CameraBroker` wrapping `pibot/ml/camera.py`'s capture in one loop, pushing to per-subscriber bounded queues (drop-oldest on overflow); refactor `AutonomyController` (`agent/autonomy.py`) to subscribe — **no behavior change** to autonomy.
- **Step 4 — run:** `pytest tests/test_camera_broker.py tests/test_autonomy_agent.py` → Expected: PASS.
- **Done when:** broker fan-out green; autonomy tests still green (resolves OQ-2 toward the shared-broker design).

### T12.2.2 — `pibotd WS /video` MJPEG endpoint (behind auth, throttled)
- **Files:** modify `agent/app.py` (`handle_ws_video` + route `app.router.add_get("/video", ...)`), `agent/video.py` (JPEG encode + throttle), `pibot/config.py` (+`video_fps`, `video_max_dim` with `_FIELD_TYPES`), `agent/__init__`/`build_app` (pass video config); test `tests/test_agent_video.py`, `tests/test_config.py` (new fields).
- **Step 1 — failing test:** `WS /video` requires the bearer (401 without); from mocked frames it emits a JSON header `{seq,ts,w,h,fmt:"jpeg"}` followed by a binary JPEG, at ≤ `video_fps`; frames are downscaled so `max(w,h) ≤ video_max_dim`; `load_config` accepts the new int fields and rejects wrong types.
- **Step 2 — run:** `pytest tests/test_agent_video.py tests/test_config.py` → Expected: FAIL.
- **Step 3 — implement:** the handler subscribes to `CameraBroker`, encodes JPEG (Pillow), throttles to `video_fps`, downscales to `video_max_dim`; behind the existing `auth_middleware` (it already gates all non-public paths).
- **Step 4 — run:** `pytest tests/test_agent_video.py tests/test_config.py && mypy agent pibot` → Expected: PASS.
- **Done when:** video endpoint green; config parity green.

### T12.2.3 — Sidecar video relay → `WS /api/video` (best-effort, droppable)
- **Files:** create `pibot/mc/video_relay.py`, `pibot/mc/routes_video.py`; modify `pibot/mc/robot_link.py` (open `WS /video` on connect), `pibot/mc/app.py`; test `tests/test_mc_video_relay.py`.
- **Step 1 — failing test:** against a fake `pibotd /video`, the relay forwards N header+binary frames to a `WS /api/video` consumer; a **slow consumer drops frames** (bounded queue, drop-oldest) and does **not** backpressure the source; killing `/api/video` does not affect the control or telemetry sockets.
- **Step 2 — run:** `pytest tests/test_mc_video_relay.py` → Expected: FAIL.
- **Step 3 — implement:** `VideoRelay` (subscribe to the robot `/video`, fan to webview WS with a small drop-oldest buffer); decouple its task from control/telemetry tasks.
- **Step 4 — run:** `pytest tests/test_mc_video_relay.py` → Expected: PASS.
- **Done when:** relay green; isolation from control proven.

### T12.2.4 — Control relay: `WS /api/control` → `pibotd WS /control` + cadence keeper
- **Files:** create `pibot/mc/routes_control.py`, `pibot/mc/cadence.py`; modify `pibot/mc/robot_link.py`; test `tests/test_mc_control.py`.
- **Step 1 — failing test:** a `{cmd:"drive",args:{v,w}}` frame over `WS /api/control` is relayed to `pibotd WS /control` and the ACK/NAK/`rejected` is returned **unchanged**; the cadence keeper re-sends the last drive at `teleop_rate_hz` so the host deadman stays fed; a clamped/NAK'd command passes through without the sidecar altering it.
- **Step 2 — run:** `pytest tests/test_mc_control.py` → Expected: FAIL.
- **Step 3 — implement:** the control WS relay over `AgentClient.send_command`; a cadence task holding the latest `(v,ω)` and re-emitting at the configured rate, cancelled on `stop`/disconnect.
- **Step 4 — run:** `pytest tests/test_mc_control.py` → Expected: PASS. Integration vs a real `pibotd`: clamp/reject parity with a direct teleop command.
- **Done when:** unit green; `tests/integration/test_mc_live.py` extended — GUI drive == teleop drive at the gate.

### T12.2.5 — Keyboard teleop (Drive screen)
- **Files:** create `app/src/stores/teleopStore.ts`, `app/src/lib/teleopMap.ts`, `app/src/screens/Drive.tsx`; tests `app/src/lib/teleopMap.test.ts`, `app/src/stores/teleopStore.test.ts`.
- **Step 1 — failing test:** `teleopMap(keys)` maps W/S→±v, A/D & arrows→±ω, with clamp to `max_v`/`max_w`; releasing all keys → `stop`; `teleopStore` emits drive frames on change and a `stop` on blur/Escape.
- **Step 2 — run:** `pnpm test` → Expected: FAIL.
- **Step 3 — implement:** the pure mapping + the store wiring to `WS /api/control`; `Drive.tsx` with a Radix layout, key capture, and a clamp display.
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** vitest green.

### T12.2.6 — Gamepad teleop (web Gamepad API)
- **Files:** create `app/src/lib/gamepadMap.ts`, `app/src/stores/gamepadStore.ts`; modify `app/src/screens/Drive.tsx`; test `app/src/lib/gamepadMap.test.ts`.
- **Step 1 — failing test:** `gamepadMap(axes, buttons)` maps left-stick Y→v, right-stick X (or left-stick X)→ω with a deadzone and the same clamp as keyboard; a face button maps to `stop`; values outside the deadzone scale linearly to the clamp.
- **Step 2 — run:** `pnpm test` → Expected: FAIL.
- **Step 3 — implement:** the pure mapping + a `requestAnimationFrame` poll loop feeding the same control path/cadence as keyboard.
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** vitest green.

### T12.2.7 — Always-on e-stop: button + global hotkey + Rust failsafe on the cached endpoint
- **Files:** modify `app/src-tauri/src/commands.rs` (`cache_robot_endpoint`, `estop_now`), `app/src-tauri/src/main.rs` (global shortcut), `app/src-tauri/Cargo.toml` (`reqwest`), `pibot/mc/robot_link.py` (call the Rust bridge on connect), `app/src/components/EstopButton.tsx`, `app/src/stores/connectionStore.ts`; tests `app/src-tauri/src/commands.rs` (`#[cfg(test)]`), `app/src/components/EstopButton.test.tsx`, integration `tests/test_mc_estop_failsafe.py`.
- **Step 1 — failing test (Rust):** after `cache_robot_endpoint({url, token})`, `estop_now()` issues `POST {url}/estop` with the bearer to a fake HTTP server **without the sidecar running**; returns ok on 2xx. **(Vitest):** the e-stop button posts `/api/estop` and renders an unmistakable latched state until cleared. **(Integration):** with the telemetry/control/video sockets killed **and** the sidecar process killed, `estop_now` still latches the robot (fake `pibotd` `/estop`).
- **Step 2 — run:** `cargo test && pnpm test && pytest tests/test_mc_estop_failsafe.py` → Expected: FAIL.
- **Step 3 — implement:** the Rust `reqwest` failsafe using the cached endpoint; the global shortcut bound to `estop_now`; the persistent `EstopButton` (primary path `POST /api/estop`, fallback to the Rust command); `RobotLink.on_connect` wired to `cache_robot_endpoint` (the M12.1 seam).
- **Step 4 — run:** the three commands → Expected: PASS.
- **Done when:** the **e-stop-under-loss** regression passes (sockets + sidecar killed) — release-blocking.

### T12.2.8 — Live video canvas + best-effort guarantee
- **Files:** create `app/src/stores/videoStore.ts`, `app/src/components/VideoCanvas.tsx`; modify `app/src/screens/Dashboard.tsx`, `app/src/screens/Drive.tsx`; test `app/src/stores/videoStore.test.ts`.
- **Step 1 — failing test:** `videoStore` decodes a header+blob frame and exposes the latest bitmap + fps; dropping/holding frames never blocks the control store (assert control dispatch latency is unaffected with a flood of video frames).
- **Step 2 — run:** `pnpm test` → Expected: FAIL.
- **Step 3 — implement:** `VideoCanvas` draws the MJPEG frame to `<canvas>` via `createImageBitmap` on `requestAnimationFrame`; `videoStore` keeps only the latest frame (drop-oldest).
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** vitest green; manual check — teleop latency unchanged with video on.

### T12.2.9 — Safety-bypass regression (release-blocking)
- **Files:** create `tests/test_mc_safety_bypass.py`; (no new product code — this proves the invariant).
- **Step 1 — failing test:** drive the sidecar control relay against a real `pibotd` (responder transport) with clamp limits set low; assert a GUI-issued `drive` beyond the clamp is **clamped/rejected exactly as a direct teleop command** (compare against `pibot/control/safety.clamp_command` expectations); assert there is **no sidecar code path** that sends a motion frame except via `AgentClient`→`pibotd` (grep-guard test over `pibot/mc`); assert a **link stall** (paused relay) triggers `pibotd`'s deadman → stop.
- **Step 2 — run:** `pytest tests/test_mc_safety_bypass.py` → Expected: FAIL (until the relay path is the only motion path).
- **Step 3 — implement:** if the test surfaces any bypass, route it through the gate; otherwise this task only adds the guard test.
- **Step 4 — run:** `pytest tests/test_mc_safety_bypass.py` → Expected: PASS.
- **Done when:** the safety-bypass regression is green and in the default suite — release-blocking.

## Milestone acceptance criteria (SPEC-3 M12.2)
Teleop command latency p95 ≤ 100 ms; video ≥ 10 fps / ≤ 400 ms glass-to-glass; e-stop works
with telemetry/video/control sockets **and** the sidecar killed; the safety-bypass test proves
no GUI command reaches the motors except through the gate.

## Risks
- **Camera contention** (R-2) → the broker is the mitigation; if the UVC path can't share, `/video` yields while autonomy holds the camera (decided by the broker test).
- **Video bandwidth degrades control** (R-3) → server `video_fps`/`video_max_dim` caps; video on its own socket; T12.2.8 proves control is unaffected; contingency = snapshot mode.
- **E-stop hole if state lived only in the sidecar** (SPEC-3 §3.2) → closed by the cached-endpoint failsafe (T12.2.7), tested with the sidecar dead.

## Definition of done
All gates green; teleop (kbd+gamepad), live video, and the always-on e-stop work; the
**safety-bypass** and **e-stop-under-loss** regressions pass and are in the default suite;
branch `m12-2-teleop-estop-video` ready to commit (ask first).
