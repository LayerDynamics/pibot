# SPEC-2 — PiBot Autonomy Platform

| | |
|---|---|
| **Spec ID** | SPEC-2 |
| **Title** | PiBot Autonomy Platform — vision-language-action (VLA) policy driving on a hardened robot runtime |
| **Status** | Draft |
| **Version** | 1.0 |
| **Author** | Ryan O'Boyle (`durbanpoisonpew@protonmail.com`) + Claude |
| **Created** | 2026-06-11 |
| **Depends on** | [SPEC-1](SPEC-1-pibot-control-suite.md) (M0–M6, shipped); [PIML.md](../../PIML.md) (integration analysis); research report `.web-research/best-os-install-pi5-robot-2026-06-11/Report-Final.md` |
| **Target repo** | `/Users/ryanoboyle/pibot` |
| **Robot platform** | Raspberry Pi 5 (8 GB) + NVMe SSD + USB camera; ESP32 wireless controller (`firmware/pibot_esp32`) |
| **Policy host** | MacBook Pro M4 Max (36 GB, Apple-Silicon MPS) — host kept swappable |

> Turn the teleoperated PiBot into a robot that **drives itself** from a camera and a
> natural-language prompt — an openpi/LeRobot VLA policy running off-robot, streaming
> safety-gated actions to a hardened, reflashed Pi runtime over the Nebula overlay.

---

## 1. Background

### 1.1 Problem Statement
PiBot today is **teleoperated**: SPEC-1's control suite (M0–M6) gives discovery, flashing, a `pibotd` agent, a CRC-framed transport to an ESP32 wireless controller, teleop, telemetry, and a layered safety subsystem — but a human is always in the loop. This spec makes PiBot **autonomous**: a vision-language-action model perceives the world through a camera, takes a language prompt ("drive to the red ball", "follow me", "explore the room"), and emits the low-level drive actions, while the robot's local safety subsystem remains the final authority. It also formalizes the **hardened runtime** the autonomy stack must sit on, because an autonomous mobile robot that corrupts its NVMe on a brown-out or wedges on a frozen kernel is worse than a teleoperated one.

### 1.2 Current State
- **SPEC-1 control suite (shipped):** `pibotd` (aiohttp HTTP/WS) owns the transport; M3 protocol/codec; M4 safety (clamp · latched e-stop · deadman watchdog); teleop/telemetry/deploy. The ESP32 firmware adds an independent firmware watchdog + link-loss stop ([firmware/pibot_esp32](../../firmware/pibot_esp32)).
- **Wireless link (built):** ESP32 wireless controller live over TCP; **Nebula overlay** (`192.168.100.x`) replaces ZeroTier for stable Mac↔Pi addressing ([nebula-overlay runbook](../runbooks/nebula-overlay.md)).
- **VLA feasibility (verified, 2026-06-11):** π₀.₅ (`lerobot/pi05_base`, 3.62 B params) runs a full forward pass on this M4 Max via PyTorch-MPS at **~760 ms / 50-action × 32-dim chunk** ([PIML.md §6](../../PIML.md)). The biggest unknown (does the brain run locally?) is resolved.
- **Runtime baseline (researched, not yet applied):** the reflash recipe — Raspberry Pi OS Lite 64-bit (Bookworm), ext4 + overlayfs, NVMe ASPM fix, dual watchdog, UPS/NUT — is documented in the research report but the Pi still runs the old image (and is currently SSH-locked-out, which the reflash fixes).
- **Not started:** the camera, the `PibotEnvironment` seam, the on-robot `openpi-client`, the server-side `PibotInputs/PibotOutputs` transforms, data collection, and fine-tuning.

### 1.3 Target Users
A **single builder-operator** (the author) running **one robot**. The same person flashes the Pi, runs the M4 Max policy server, collects demonstrations, fine-tunes, and operates the robot. No fleet, no multi-tenant, no external consumers.

### 1.4 Motivation
Three converging drivers (all confirmed in discovery): **(a)** make PiBot drive itself (VLA autonomy); **(b)** make it reliable and reflashable (fix the SSH-lockout class of problems for good and survive power loss as a mobile robot); **(c)** collect data to train policies for it. Vision (a USB camera) is the enabling addition — a VLA is vision-conditioned, so the camera is a hard requirement, not an option. The opportunity is concrete and de-risked: the model already runs on hardware we own, at no cloud cost.

### 1.5 Assumptions
- The M4 Max is awake and reachable over Nebula whenever the robot is autonomous (PIML §7.1).
- π₀.₅ requires a **PiBot fine-tune** to produce useful actions; zero-shot on a wheeled rover is out-of-distribution (PIML §7.2).
- The Pi 5 cannot run the model; it runs only the lightweight `openpi-client` (PIML §1, §2).
- A 224×224 RGB observation + a low-dim robot-state vector + a text prompt is a sufficient observation for the target tasks.
- The differential-drive action space (`[v, ω]` + optional servos) can be mapped to/from the model's action columns via server-side transforms (PIML §4).

---

## 2. Requirements

### 2.1 Functional Requirements

| ID | Priority | Requirement |
|----|----------|-------------|
| FR-1 | MUST | The system MUST capture RGB frames from a **USB UVC camera** and produce a 224×224 `uint8` observation image via `image_tools.resize_with_pad` + `convert_to_uint8`. |
| FR-2 | MUST | The system MUST assemble an observation dict `{image: {base_0_rgb}, state, prompt}` each control step from the camera frame + M3 telemetry (robot state). |
| FR-3 | MUST | The system MUST run the `openpi-client` `Runtime` loop inside `pibotd`, driving a remote policy via `WebsocketClientPolicy` wrapped in `ActionChunkBroker`. |
| FR-4 | MUST | Every policy-emitted action MUST pass the M4 safety gate (clamp + latched e-stop + deadman) **before** actuating; the policy MUST NOT bypass local safety. |
| FR-5 | MUST | The robot MUST stop within the deadman window if the policy stream stalls or the link drops, **independent** of the VLA (host deadman + firmware watchdog backstop). |
| FR-6 | MUST | The system MUST map a model action vector → PiBot differential-drive `drive(v, ω)` (+ optional `servo(id, deg)`) frames over the M3 protocol (`_action_to_command`). |
| FR-7 | MUST | A policy server MUST serve a π₀.₅ checkpoint over websocket `:8000`, reachable from the Pi over the Nebula overlay; the V1 host is the **M4 Max (PyTorch-MPS)**. |
| FR-8 | MUST | The on-robot client MUST run on the **reflashed hardened runtime** (Bookworm + research hardening), with ML deps (`openpi-client`, `numpy<2.0`) isolated in an optional `pibot[ml]` extra so the core suite stays stdlib-light. |
| FR-9 | MUST | The system MUST support **language-prompted multi-task** behavior — drive-to-visual-goal, follow, and explore — selected by the observation `prompt`. |
| FR-10 | MUST | The system MUST record teleop **demonstrations** (obs + action per step) and convert them to a **LeRobot dataset** for fine-tuning. |
| FR-11 | SHOULD | The system SHOULD provide an **open-loop mode** (stream real obs, log returned actions, do NOT actuate) as a bring-up gate before any closed-loop motion (PIML Phase 1). |
| FR-12 | SHOULD | The system SHOULD **fine-tune** π₀.₅ on PiBot demonstrations (server-side `PibotInputs/PibotOutputs` + norm stats) and serve the new checkpoint (PIML Phase 2). |
| FR-13 | SHOULD | The system SHOULD record per-inference `server_timing` + measured round-trip latency for monitoring. |
| FR-14 | SHOULD | The policy-server host SHOULD remain **swappable** (M4 Max now, NVIDIA GPU/cloud later) — the client depends only on `host:port`. |
| FR-15 | COULD | The system COULD add an **MLX serving route** as an optimization if PyTorch-MPS op-coverage or perf proves inadequate (build-it-yourself; no π₀ MLX port exists). |
| FR-16 | COULD | The system COULD support a second camera viewpoint. |
| FR-17 | WONT | The system WILL NOT run the VLA model on the Pi (GPU model; the Pi runs only the client). |
| FR-18 | WONT | The system WILL NOT actuate from a **stock (non-fine-tuned)** policy in closed loop — closed-loop motion requires a PiBot fine-tune. |
| FR-19 | WONT | The system WILL NOT replace or weaken the M4 safety subsystem — the VLA always sits behind it. |

### 2.2 Non-Functional Requirements

#### Performance
| Metric | Target | Measurement |
|--------|--------|-------------|
| Control loop rate | ≥ 20 Hz sustained | `Runtime(max_hz=20)`; ActionChunkBroker emits 1 action/step |
| Inference latency | ≤ ~1 s / chunk (measured ~760 ms, π₀.₅ MPS) | server `server_timing` + client round-trip |
| Motion per inference | ≥ 50 actions ≈ ≥ 2.5 s @ 20 Hz → ≤ ~30 % compute duty cycle | `action_horizon = 50` |
| Camera capture | ≥ 15 fps; obs assembly ≤ 50 ms/step on the Pi | timed in `get_observation` |
| Fresh-chunk action latency | ≤ ~1.2 s (obs → first actuation of a new chunk); hidden by chunking thereafter | end-to-end timer |

#### Reliability
| Metric | Target |
|--------|--------|
| Drop-to-stop | Robot halts ≤ 300 ms (host deadman) with firmware-watchdog backstop, on policy stall or link drop |
| Power-loss resilience | 0 rootfs corruptions over a yanked-power test campaign (overlayfs RO root) |
| NVMe stability | 0 read-only-remount events with `pcie_aspm=off nvme_core.default_ps_max_latency_us=0` |
| Autonomy availability | Best-effort (single robot; Mac must be awake/reachable) — no HA target |

#### Security & Compliance
- **Transport:** Mac↔Pi over the **Nebula** overlay (certificate-based, encrypted); keys gitignored.
- **Policy websocket:** optional `api_key` on `WebsocketClientPolicy`/server.
- **Agent:** M4 bearer-token auth + loopback trust unchanged; tokens `0600`, never committed.
- **Data classification:** demonstration video/state of the operator's own space — treat as private; datasets are local, not published.
- **Compliance:** none (personal project). **Gemma license** applies to π₀ weights for any product/redistribution use (PIML §1, §7.7).

#### Scalability
Single robot, single operator. No horizontal scaling; the only "scale" axis is dataset size for fine-tuning. Explicitly **not** a fleet platform.

### 2.3 Constraints
- **Pi 5 cannot run the model** (GPU/Apple-Silicon model) → a remote policy server is mandatory (PIML §1).
- **`numpy < 2.0`** pin from `openpi-client` → ML deps must live in an optional extra to protect the core suite (PIML §7.5).
- **Apple-Silicon path = PyTorch-MPS** (verified); MLX has no π₀ implementation (build-it-yourself) (PIML §6).
- **No zero-shot** — a PiBot fine-tune is required before closed-loop actuation (PIML §7.2).
- **Runtime baseline** is Raspberry Pi OS Lite 64-bit (Bookworm), ext4, PCIe Gen 2, per the research report (NOT Ubuntu, NOT ROS 2, NOT f2fs).

### 2.4 Explicit Non-Goals
- On-Pi model inference; ROS 2; multi-robot/fleet; manipulation-arm tasks (PiBot is a rover); a cloud-GPU dependency for V1; replacing the M4 safety subsystem; publishing datasets/weights.

---

## 3. Architecture

### 3.1 System Overview
A **remote-brain / on-robot-client** split (openpi's native client-server model), one network hop over Nebula, with the VLA strictly **behind** the local safety subsystem.

```text
┌──────────────── Raspberry Pi 5 (PiBot, on-robot, Bookworm + overlayfs) ───────────────┐
│  pibotd (SPEC-1 M4 agent) — sole transport owner                                      │
│   openpi_client.runtime.Runtime  loop @ 20 Hz                                          │
│     get_observation ─► policy.get_action ─► apply_action                              │
│   ┌─ Camera (USB UVC) ─► resize_with_pad 224×224 uint8 ─┐                              │
│   ├─ PibotEnvironment (NEW)  obs={image,state,prompt}   │                              │
│   ├─ ActionChunkBroker  (1 action/step; re-query每50)    │                              │
│   ├─ WebsocketClientPolicy (msgpack+numpy)              │                              │
│   └─ apply_action ─► _action_to_command ─► M4 SAFETY GATE ─► M3 protocol ─► ESP32      │
│        (clamp · latched e-stop · deadman)   firmware watchdog = independent backstop   │
│   subscribers=[EpisodeLogger] ─► LeRobot dataset (for fine-tuning)                     │
└───────────────────────────────────┼────────────────────────────────────────────────────┘
                                     │  websocket :8000  (Nebula overlay 192.168.100.x)
                                     ▼
┌──────── Policy server: M4 Max (36 GB, MPS) ── host swappable ► NVIDIA GPU later ───────┐
│  openpi.serving.WebsocketPolicyServer  (emits server_timing)                          │
│   π₀.₅ checkpoint  +  PibotInputs / PibotOutputs transforms  +  norm stats            │
│   scripts/serve_policy.py --policy.config=pibot --policy.dir=<ckpt>  (pytorch mps)     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Design

#### Component: Camera module — `pibot/ml/camera.py`
- **Responsibility:** capture RGB frames from a USB UVC camera and return a 224×224 `uint8` array.
- **Technology:** OpenCV/`v4l2` capture; `openpi_client.image_tools` for resize/pad/convert. Pillow + numpy only on the Pi.
- **Interfaces:** `capture() -> np.ndarray (224,224,3) uint8`; `start()/stop()`.
- **Dependencies:** a USB camera at `/dev/video0`; `pibot[ml]` extra.

#### Component: PibotEnvironment — `pibot/ml/pibot_environment.py`
- **Responsibility:** implement openpi's `Environment` ABC (`reset`, `is_episode_complete`, `get_observation`, `apply_action`) — the seam between the model and PiBot.
- **Technology:** `openpi_client.runtime.environment`.
- **Interfaces:** `get_observation() -> {image:{base_0_rgb}, state, prompt}`; `apply_action({actions})`.
- **Dependencies:** Camera module, M3 transport (read state / send commands), M4 safety gate.

#### Component: Action↔command mapper — `_action_to_command` (in PibotEnvironment)
- **Responsibility:** translate a per-step model action vector → `drive(v, ω)` / `servo(id, deg)` M3 frames (PiBot's differential-drive action space).
- **Interfaces:** `_action_to_command(vec) -> Message`.

#### Component: Policy client wiring — inside `pibotd`
- **Responsibility:** construct `ActionChunkBroker(WebsocketClientPolicy(host, 8000), action_horizon=50)`, the `Runtime`, the `PolicyAgent`, and the `EpisodeLogger` subscriber; own the run loop.
- **Dependencies:** `openpi-client`, the Nebula endpoint from `~/.config/pibot/config.toml`.

#### Component: Safety gate — SPEC-1 M4 (reused, unchanged)
- **Responsibility:** clamp + latched e-stop + deadman watchdog on every actuation; the only path to the motors.
- **Interfaces:** `AgentSafety.submit`/`tick`/`trip_estop`.

#### Component: Episode logger — `pibot/ml/episode_logger.py`
- **Responsibility:** record `(observation, action, timestamp)` per step (a `Runtime` subscriber) and convert to a **LeRobot dataset**.
- **Technology:** LeRobot dataset format; openpi `convert_*_to_lerobot.py` as template.

#### Component: Policy server — `server/` (on the M4 Max)
- **Responsibility:** serve π₀.₅ with PiBot transforms over websocket :8000.
- **Technology:** `openpi.serving.WebsocketPolicyServer`, `scripts/serve_policy.py`, **PyTorch-MPS** (`pytorch_device="mps"`); `transformers==4.53.2` + openpi `transformers_replace` patch (per the verified recipe).
- **Interfaces:** `infer(obs) -> {actions}` over msgpack+numpy.
- **Dependencies:** π₀.₅ checkpoint, `PibotInputs/PibotOutputs`, norm stats, gated PaliGemma tokenizer (`HF_TOKEN`).

#### Component: PibotPolicy transforms + norm stats — server-side
- **Responsibility:** `PibotInputs` packs PiBot obs into the model dict; `PibotOutputs` slices model action columns → `[v, ω, servo…]`; `compute_norm_stats.py` for PiBot ranges.
- **Template:** openpi `examples/ur5/README.md` + `src/openpi/policies/`.

#### Component: Fine-tuning pipeline — `server/` (M4 Max or a GPU box)
- **Responsibility:** fine-tune π₀.₅ on the PiBot LeRobot dataset, produce a checkpoint to serve.

#### Component: Hardened runtime (the platform) — reflash + provisioning
- **Responsibility:** the reproducible on-robot OS the autonomy stack runs on: Bookworm Lite 64-bit, ext4 + overlayfs RO-root + small `rw` partition, NVMe ASPM fix, dual watchdog, journald-volatile + log-shipping, UPS/NUT, hardened Nebula unit, `pibotd` + ml-client as systemd services. Flashed via the SPEC-1 `pibot flash --os rpi-os` path with first-boot SSH-key embedding.

#### Component: Nebula overlay (reused)
- **Responsibility:** encrypted, stable Mac↔Pi addressing for the policy link (and SSH/deploy).

### 3.3 Data Model
- **Observation:** `{"image": {"base_0_rgb": uint8[224,224,3]}, "state": float[2], "prompt": str}`. **state = `[v, ω]`** — the last commanded velocity (the rover's proprioceptive motion state; the current firmware has no encoders/IMU, so last-velocity is the meaningful proprioception). `state_dim = 2` (OQ-2, resolved 2026-06-12); extends if the firmware gains encoders/IMU.
- **Action chunk (server → client):** `{"actions": float[action_horizon, 2]}`; the broker emits one `float[2]` per step. **action = `[v, ω]`** (`action_dim = 2`) → `drive(v, ω)` via `PibotOutputs`. The firmware's 2 servos are excluded from the V1 action space (extensible).
- **Demonstration dataset:** LeRobot episodes — sequences of `(observation, action, timestamp)`; one episode per recorded teleop run, tagged with the task prompt.
- **Lifecycle:** obs is ephemeral (per step); demonstrations are appended during collection, converted to a dataset, consumed by fine-tuning, then immutable; checkpoints are versioned on the server.

### 3.4 API & Interface Design
- **Policy websocket** (`openpi-client` ↔ server): msgpack+numpy; `policy.infer(obs) -> {actions, server_timing, …}`; optional `api_key`. Port 8000, `0.0.0.0` bind on the server, reached at the Mac's Nebula IP.
- **On-robot control:** unchanged M3 CRC-framed protocol (`drive`/`servo`/`stop`/`estop`) over the existing transport to the ESP32.
- **Config:** `~/.config/pibot/config.toml` gains `policy_host`, `policy_port`, `action_horizon`, `control_hz`, `camera_device`, `prompt` (defaults; overridable per run).
- The exact observation/action JSON contract is in **Appendix B**.

### 3.5 Data Flow
**Closed-loop autonomy (steady state):** camera frame → `resize_with_pad` 224×224 → obs dict (+ M3 state + prompt) → (every 50 steps) `WebsocketClientPolicy.infer` over Nebula → server runs π₀.₅ (PibotInputs → model → PibotOutputs) → 50-action chunk → `ActionChunkBroker` emits 1 action/step → `_action_to_command` → **M4 safety gate** → M3 frame → ESP32 actuates. In parallel, the `EpisodeLogger` records each `(obs, action)`.

**Bring-up (open-loop):** identical except `apply_action` logs the action and does **not** send it to the transport.

**Data collection:** M4 teleop drives; the same `EpisodeLogger` records `(obs, action)`; convert → LeRobot dataset → fine-tune.

### 3.6 Integration Points
- **openpi/LeRobot** (`resources/openpi`) — client on the Pi, server + transforms on the Mac.
- **Hugging Face** — π₀.₅ checkpoint (`lerobot/pi05_base`) + gated PaliGemma tokenizer (`HF_TOKEN`).
- **SPEC-1 suite** — transport (M3), agent + safety + telemetry (M4), deploy (M5), flash/provision (M2) for the reflash.
- **Nebula** — the overlay link.

### 3.7 Security Architecture
- **Link:** Nebula (cert-based, encrypted) for the policy websocket + SSH/deploy; lighthouse on the Pi, hardened `Restart=always` units.
- **AuthN/Z:** optional websocket `api_key`; M4 bearer token for the agent HTTP/WS; loopback trust for local.
- **Secrets:** WiFi creds (`secrets.h`), Nebula keys, `HF_TOKEN`, agent token — all `0600` and gitignored; never in the repo (enforced by the M6 security-invariants test).
- **Data:** demonstrations are private and local.

### 3.8 Resilience Design
- **Layered fail-safe (unchanged, load-bearing):** (1) operator e-stop; (2) host deadman watchdog stops the robot if the policy/command stream stalls ≤ 300 ms; (3) **independent ESP32 firmware watchdog** halts motors if the Pi/link dies — the VLA is never the only thing between perception and the motors (PIML §7.4).
- **Dropped link:** action chunking hides *throughput*, not a *dropped link* — a stalled `infer` → no new chunk → deadman fires.
- **Runtime:** overlayfs RO-root survives power loss; NVMe ASPM disabled; UPS/NUT graceful shutdown; auto-restarting `pibotd`/nebula systemd units.
- **Policy server down / Mac asleep:** the robot cannot get actions → it stops (fail-safe), it does not coast.

### 3.9 Observability
- **Latency:** server emits `server_timing` per inference; client logs round-trip; surfaced in `pibot monitor`.
- **Episodes:** the `EpisodeLogger` records obs/action for fine-tuning and post-hoc review.
- **Logs:** journald volatile on the Pi, **shipped to the Mac over Nebula** for field post-mortems (research recommendation).
- **Health:** existing `/telemetry` snapshot extended with policy-link status (connected / last-inference-ms / chunk-age).

### 3.10 Infrastructure & Deployment
- **Robot:** reflashed Bookworm Lite 64-bit via `pibot flash --os rpi-os` (first-boot key embedding) → apply the research hardening → `pibot deploy` installs `pibotd` + the `pibot[ml]` client extra as systemd services.
- **Server:** the M4 Max runs `serve_policy.py` (or under a launchd/process manager) bound to its Nebula IP:8000; checkpoints stored locally.
- **CI:** the SPEC-1 gate (ruff/format/mypy/pytest, hardware/toolchain deselected) extended with `pibot[ml]` import/unit tests (mocked camera + fake websocket policy); model inference stays off CI (hardware/host-marked).

---

## 4. Implementation Plan

### 4.1 Build Phases

#### Phase A — Hardened runtime + prove-the-pipe (PIML Phase 0)
- **Goal:** a trustworthy reflashed Pi that round-trips the policy websocket.
- **Scope:** reflash to Bookworm + apply the research hardening (overlayfs, ASPM fix, dual watchdog, UPS/NUT, Nebula unit); install `openpi-client` (`pibot[ml]`); run openpi `simple_client` against the M4 Max server with random obs; measure round-trip latency over Nebula.
- **Exit criteria:** SSH-key login works (lockout fixed); `simple_client` round-trips; latency recorded; a yanked-power test leaves rootfs intact.

#### Phase B — Camera + observation pipeline, open loop (PIML Phase 1)
- **Goal:** real observations to a stock π₀.₅, no motion.
- **Scope:** USB camera module + `PibotEnvironment.get_observation`; stream real obs to a stock-checkpoint server; **log returned actions, do NOT actuate** (FR-11).
- **Exit criteria:** obs schema validated against the server; image pipeline ≥ 15 fps; end-to-end latency on real data measured; zero actuation.

#### Phase C — Server transforms + data collection
- **Goal:** the PiBot policy config + a demonstration dataset.
- **Scope:** server-side `PibotInputs/PibotOutputs` + `compute_norm_stats`; record teleop demonstrations for the three tasks (drive-to-goal, follow, explore) → LeRobot dataset.
- **Exit criteria:** a dataset with demonstrations per task; norm stats computed; transforms round-trip an obs→action without shape errors.

#### Phase D — Fine-tune + closed loop, safety-gated (PIML Phase 2)
- **Goal:** the robot drives itself on ≥ 1 prompted task.
- **Scope:** fine-tune π₀.₅ on the dataset; serve the checkpoint; implement `apply_action` → M3 **through the M4 safety gate**; run closed-loop with the watchdog armed.
- **Exit criteria:** closed-loop completion of ≥ 1 task with drop-to-stop verified; the policy never bypasses safety (test-proven).

#### Phase E — Multi-task + hardening/observability
- **Goal:** all three prompted behaviors + operability.
- **Scope:** demonstrations + fine-tune covering follow + explore; policy-link telemetry in `pibot monitor`; runbooks (autonomy bring-up, fine-tune, data collection).
- **Exit criteria:** all three prompts produce their behavior; latency/link dashboards; runbooks pass doc-lint.

### 4.2 Testing Strategy
- **Unit:** camera module (mocked frames → 224×224), `PibotEnvironment` (`_action_to_command` mapping; obs schema), action-chunk emission, episode logger (mocked steps → dataset rows). No network/model.
- **Integration:** `PibotEnvironment` against a **fake websocket policy** (returns canned chunks) end-to-end through the M4 safety gate using the responder transport — proving the model can never bypass safety, and that a stalled policy triggers drop-to-stop (mirrors the M4 in-process drop-to-stop E2E).
- **HIL / host-marked:** real `simple_client` ↔ M4 Max server (latency); real camera capture; real closed-loop on the robot (manual, hardware-marked, deselected by default like SPEC-1's `hardware`/`toolchain` tests).
- **Safety regression:** a test asserting a policy-emitted motion is clamped/rejected exactly as a teleop command, and that link-stall → stop.

### 4.3 Rollout Strategy
Phase-gated, each phase independently valuable (PIML §8). **Open-loop (Phase B) is a hard gate before any closed-loop motion.** Closed-loop runs start tethered/low-speed with the e-stop in hand; clamp limits reduced for first runs. Rollback = serve the previous checkpoint / `pibot deploy --rollback` / fall back to teleop.

### 4.4 Operational Readiness
Before any unattended autonomy: drop-to-stop verified on hardware; firmware watchdog confirmed; UPS shutdown tested; policy-link telemetry visible; runbooks written; the Mac's thermal/power load under sustained inference characterized (PIML §6 operational note).

---

## 5. Milestones

| Milestone | Goal | Exit Criteria | Owner |
|-----------|------|---------------|-------|
| **M7 — Hardened runtime + pipe** | Reflashed Pi + websocket round-trip | Lockout fixed; `simple_client` round-trips; latency logged; power-yank survives | Ryan |
| **M8 — Camera + open loop** | Real obs, no motion | Camera ≥15 fps; obs schema validated; actions logged, zero actuation | Ryan |
| **M9 — Transforms + data** | PiBot policy config + dataset | `PibotInputs/Outputs` + norm stats; LeRobot dataset for 3 tasks | Ryan |
| **M10 — Fine-tune + closed loop** | Robot drives 1 task | Fine-tuned ckpt served; ≥1 task closed-loop; drop-to-stop + safety-bypass tests pass | Ryan |
| **M11 — Multi-task + ops** | 3 behaviors + observability | drive-to-goal + follow + explore work; link telemetry; runbooks lint-clean | Ryan |

### Dependency Graph
```text
SPEC-1 (M0–M6, done)
      │
      ▼
   M7 ──► M8 ──► M9 ──► M10 ──► M11
 runtime  cam    xforms  fine-   multi-
 + pipe   open   + data  tune+   task+
          loop          closed   ops
```

---

## 6. Success Criteria

### 6.1 Launch Metrics
| Metric | Target | Measurement Method |
|--------|--------|--------------------|
| Closed-loop task success | ≥ 60 % over ≥ 20 trials per task *(target to confirm — OQ-1)* | manual trial log |
| Drop-to-stop | 100 % (every stalled-link trial stops the robot) | HIL test + e-stop trials |
| Power-loss corruption | 0 over the yank-test campaign | repeated yank + fsck/boot |
| Inference duty cycle | ≤ 30 % at 20 Hz | `server_timing` vs chunk wall-time |
| Round-trip latency (Nebula) | ≤ ~1 s p95 | client timer |

### 6.2 Ongoing Monitoring
`pibot monitor` shows policy-link status (connected, last-inference-ms, chunk-age) alongside SoC/battery/transport/e-stop. Logs shipped to the Mac. Review cadence: per-session (it's one operator, one robot).

### 6.3 Remediation Triggers
- Any closed-loop run where drop-to-stop fails → **halt autonomy work**, fix the watchdog path first.
- Inference p95 > 1.5 s or duty cycle > 50 % → revisit `action_horizon` / serving route (consider MLX track).
- Any NVMe read-only remount or rootfs corruption → stop, re-verify the ASPM fix + overlayfs.

---

## 7. Risks

| ID | Risk | Impact | Likelihood | Mitigation | Contingency |
|----|------|--------|-----------|------------|-------------|
| R-1 | Apple-Silicon **MPS op-coverage** gaps in π₀.₅ forward/denoise | High | Medium | `PYTORCH_ENABLE_MPS_FALLBACK=1`; verified base forward pass already runs (PIML §6) | Move serving to a rented/owned NVIDIA GPU (host is swappable, FR-14) |
| R-2 | **Zero-shot fails** — rover is out-of-distribution for π₀.₅ | High | High (expected) | Plan for data collection + fine-tune from the start (Phases C–D); never closed-loop on a stock ckpt (FR-18) | More demonstrations / smaller task scope per prompt |
| R-3 | **Dropped policy link** mid-motion | High (safety) | Medium | Independent host deadman + ESP32 firmware watchdog stop the robot; chunking does not mask a drop (FR-5, §3.8) | Reduce speed/clamp; tether for first runs |
| R-4 | **`numpy<2.0`** / ML deps destabilize the core suite | Medium | Low | Isolate in `pibot[ml]` optional extra; core stays stdlib-light (FR-8) | Pin/contain; the core CLI/agent never import ml |
| R-5 | **Mac unavailable** (asleep/thermal) during autonomy | Medium | Medium | Robot fails safe (no actions → stops); document the awake-and-reachable requirement | Dedicated GPU host; caffeinate/power settings |
| R-6 | **Camera latency/quality** (USB UVC) degrades obs | Medium | Medium | ≥15 fps budget; measure obs assembly ≤50 ms; consider Pi Camera Module 3 if UVC underperforms | Switch camera; lower control_hz |
| R-7 | **NVMe/power-loss** corruption on a mobile robot | High | Medium | overlayfs RO-root, ASPM fix, ext4, UPS/NUT, 27 W PSU (research recipe) | SD fallback; A/B image |
| R-8 | **Action-space mapping** (manipulator-trained model → diff-drive) is wrong | High | Medium | Server `PibotInputs/PibotOutputs` (UR5 template) + norm stats; validate open-loop first | Re-define the action columns; collect more data |
| R-9 | **Gemma license** constraints for any product use | Low | Low | Personal/research use; review terms before any redistribution | N/A for personal use |

---

## 8. Open Questions

| # | Question | Owner | Due |
|---|----------|-------|-----|
| OQ-1 | Exact closed-loop success-rate target + trial count per task | Ryan | before M10 |
| OQ-2 | ✅ RESOLVED (2026-06-12): `state = [v, ω]` (last commanded velocity, dim 2), `action = [v, ω]` (dim 2); servos excluded from V1 (no encoders/IMU in firmware). Revisit if encoders/IMU/servos are added. | Ryan | done |
| OQ-3 | USB camera model, FOV, and mounting position (forward-facing height/angle) | Ryan | M8 |
| OQ-4 | Number of demonstrations per task needed for a usable fine-tune | Ryan | M9 |
| OQ-5 | Add an `api_key` on the policy websocket, or rely on Nebula encryption alone? | Ryan | M10 |
| OQ-6 | MLX track trigger — what MPS latency/op-coverage threshold justifies the port? | Ryan | post-M11 |
| OQ-7 | Fine-tune host — M4 Max (LoRA/low-mem) vs a rented GPU for the full run | Ryan | M9 |

---

## Appendices

### Appendix A — Glossary
- **VLA** — vision-language-action model (camera + text → action chunk).
- **π₀ / π₀.₅** — Physical Intelligence's flow-based VLA models; π₀.₅ has better open-world generalization. PiBot uses `lerobot/pi05_base` (3.62 B).
- **Action chunk / `ActionChunkBroker`** — the server returns a horizon of future actions per inference; the broker emits one per control step and re-queries every `action_horizon` steps, hiding remote-inference latency.
- **`openpi-client`** — the light Pi-side package (dm-tree, msgpack, numpy<2.0, pillow, websockets; no jax/torch/CUDA).
- **`PibotEnvironment`** — PiBot's implementation of openpi's `Environment` ABC.
- **`PibotInputs/PibotOutputs`** — server-side transforms mapping PiBot obs/actions ↔ the model's expected tensors.
- **overlayfs RO-root** — read-only root + RAM upper layer for power-loss-proof storage (research recipe).
- **Nebula** — Slack's certificate-based overlay mesh (the Mac↔Pi link).
- **Deadman / firmware watchdog** — the layered fail-safe stopping the robot on stall/drop.

### Appendix B — Observation / Action contract
```jsonc
// observation (client -> server)
{
  "image": { "base_0_rgb": "uint8[224,224,3]" },
  "state": "float[2]",              // [v, w] — last commanded velocity (OQ-2 resolved)
  "prompt": "string"                // e.g. "drive to the red ball" | "follow me" | "explore"
}
// inference reply (server -> client)
{
  "actions": "float[action_horizon, 2]",  // each step -> [v, w] -> drive(v, w) via PibotOutputs
  "server_timing": { "infer_ms": "float" }
}
```

### Appendix C — Decision Log
| # | Decision | Rationale | Source |
|---|----------|-----------|--------|
| D-1 | Camera = **USB UVC webcam** | Operator choice; flexible/portable | discovery 2026-06-11 |
| D-2 | Tasks = **drive-to-goal + follow + explore** (language-prompted, multi-task) | Operator choice ("all of the above") | discovery |
| D-3 | V1 scope = **open-loop → then closed-loop fine-tuned** (full arc, open-loop as gate) | Operator choice ("one and two") | discovery |
| D-4 | Policy host = **M4 Max (PyTorch-MPS), kept swappable** | Operator choice ("both"); verified MPS run | discovery + PIML §6 |
| D-5 | Runtime OS = **Raspberry Pi OS Lite 64-bit (Bookworm)**, no ROS 2, ext4+overlayfs | Research report recommendation | research 2026-06-11 |
| D-6 | VLA sits **behind** the M4 safety gate; never bypasses | Safety-first; PIML §7.4 | PIML.md |

### Appendix D — Runbooks (pointers)
- Reflash recipe + hardening → research report `Report-Final.md` (10-step checklist).
- Remote link → [docs/runbooks/nebula-overlay.md](../runbooks/nebula-overlay.md).
- First-boot key embedding (fixes the lockout) → [docs/runbooks/first-boot.md](../runbooks/first-boot.md).
- e-stop / fail-safe → [docs/runbooks/e-stop.md](../runbooks/e-stop.md).
- *To write (Phase E):* autonomy bring-up, data collection, fine-tune-and-serve.
