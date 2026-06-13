# Plan — M12.3: Autonomy + Policy-Server Management

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. Note adjacent issues as TODOs; do NOT fix them.

**Goal:** Launch and watch closed-loop VLA autonomy from the GUI, and manage the openpi policy server (start/stop/health, checkpoint selection, live latency) on the host.
**Architecture:** The sidecar drives `pibotd`'s in-process `/autonomy` (start/stop/status) via `AgentClient`, and manages a local `serve_policy.py` subprocess as the policy brain. The webview shows the policy-link health that already flows in the telemetry snapshot (`policy:{connected,last_inference_ms,chunk_age_ms}`). The robot still drives through the unchanged on-Pi safety gate.
**Tech Stack:** aiohttp (sidecar), Python subprocess management, openpi `serve_policy.py` (`resources/openpi/scripts/serve_policy.py`), React/Zustand + Radix Slider, a charting lib (Recharts or uPlot).
**Practices:** TDD + typed-first + contract-first.
**Required skills:** none.

| | |
|---|---|
| **Spec** | [SPEC-3](../specs/SPEC-3-pibot-mission-control.md) FR-11, FR-12, FR-13; §3.5 (autonomy/policy flows); §4.1 P3; §5 M12.3 |
| **Phase** | P3 (autonomy) |
| **Depends on** | M12.2 (live ops, e-stop, video) |
| **Branch** | `m12-3-autonomy-policy-server` |
| **Date** | 2026-06-12 |
| **Status** | Software complete in the working tree (T12.3.1–T12.3.5; Python/frontend/Rust suites green) but **UNCOMMITTED** on branch `m12-2-teleop-estop-video`. Autonomy screen mounted in the App shell (frontend integration, 2026-06-12). Host-marked: T12.3.6 integration (deselected in CI). |

## In scope
The sidecar `/api/autonomy` (→ `pibotd /autonomy`); the policy-server manager
(`/api/policy-server`) over a local `serve_policy.py` subprocess; the Autonomy screen
(prompt/task, `max_speed`, `control_hz`, live policy-link health + latency chart); the
policy-server UI (start/stop/health, checkpoint pick); an end-to-end autonomy round-trip
against a fake websocket policy through the real safety gate.

## Out of scope
Data/dataset/fine-tune (M12.4); provisioning (M12.5). Running a real model in CI (host-marked
only). Remote policy hosts (SPEC-3 OQ-9, post-V1) — V1 manages the **local** server (the M4 Max
is the app host, SPEC-3 §1.5).

## Prerequisites
- M12.2 done; the SPEC-2 autonomy path live (`agent/autonomy.py` `AutonomyController`; `pibotd` `POST/GET/DELETE /autonomy`; `AgentClient.autonomy_start/stop`).
- `resources/openpi/scripts/serve_policy.py` present (verified); the serve command is documented in `docs/runbooks/finetune-and-serve.md`.

## Contracts (define first — contract-first)
```python
# pibot/mc/policy_server.py — typed-first.
from dataclasses import dataclass
@dataclass
class PolicyServerState:
    host: str; port: int; pid: int | None
    checkpoint: str | None; state: str   # "stopped" | "starting" | "running" | "error"
    last_infer_ms: float | None
# serve command (from docs/runbooks/finetune-and-serve.md), spawned as a managed subprocess:
#   python resources/openpi/scripts/serve_policy.py --policy.config=pibot --policy.dir=<ckpt> ...
```
```ts
// app/src/lib/api/autonomy.ts
export interface AutonomyStart { prompt: string; max_speed?: number; control_hz?: number }
export interface PolicyLink { connected: boolean | null; last_inference_ms: number | null; chunk_age_ms: number | null }
```

## Tasks

### T12.3.1 — Sidecar `/api/autonomy` (start/stop/status → `pibotd /autonomy`)
- **Files:** create `pibot/mc/routes_autonomy.py`; modify `pibot/mc/robot_link.py` (expose `autonomy_start/stop/status`), `pibot/mc/app.py`; test `tests/test_mc_autonomy.py`.
- **Step 1 — failing test:** `POST /api/autonomy{prompt,max_speed,control_hz}` calls `AgentClient.autonomy_start` with exactly those args; `DELETE /api/autonomy` calls `autonomy_stop`; `GET /api/autonomy` returns `{running, policy}` from the telemetry snapshot's `policy` block.
- **Step 2 — run:** `pytest tests/test_mc_autonomy.py` → Expected: FAIL.
- **Step 3 — implement:** the routes delegating to `AgentClient` (against a fake `pibotd /autonomy` like SPEC-2's fakes); typed `AutonomyStart`.
- **Step 4 — run:** `pytest tests/test_mc_autonomy.py && mypy pibot/mc` → Expected: PASS.
- **Done when:** green; arg-forwarding parity proven.

### T12.3.2 — Policy-server manager (`serve_policy.py` subprocess)
- **Files:** create `pibot/mc/policy_server.py`, `pibot/mc/routes_policy_server.py`; modify `pibot/mc/app.py`; test `tests/test_mc_policy_server.py`.
- **Step 1 — failing test:** with a **fake server binary** (a stub script that listens and prints a ready line — injected via a `serve_cmd` factory, never the real model in CI), `POST /api/policy-server{checkpoint}` spawns it and reports `state:"running"` + `pid` + `checkpoint`; `GET` polls health/`last_infer_ms`; `DELETE` terminates it (and on timeout, kills the process group); serving a different checkpoint = stop + respawn with the new `--policy.dir`.
- **Step 2 — run:** `pytest tests/test_mc_policy_server.py` → Expected: FAIL.
- **Step 3 — implement:** `PolicyServerManager` (build the argv from the runbook command + `resources/openpi/scripts/serve_policy.py`; spawn in its own process group; health via a TCP/HTTP probe to `policy_port`; track `last_infer_ms` from the telemetry `policy` block). The real serve command is host-marked; the unit tests use the injected fake.
- **Step 4 — run:** `pytest tests/test_mc_policy_server.py && mypy pibot/mc` → Expected: PASS.
- **Done when:** green; start/stop/respawn-on-checkpoint proven with a fake process.

### T12.3.3 — Autonomy screen: prompt/task + clamp + live policy-link
- **Files:** create `app/src/stores/autonomyStore.ts`, `app/src/screens/Autonomy.tsx`, `app/src/lib/tasks.ts`; tests `app/src/stores/autonomyStore.test.ts`, `app/src/lib/tasks.test.ts`.
- **Step 1 — failing test:** `tasks` mirrors `pibot/config.py` `TASK_PROMPTS` (`goal`/`follow`/`explore` → the canonical strings); `autonomyStore` reduces the telemetry `policy` block and flags **stale** when `chunk_age_ms > 1000`; starting posts `{prompt,max_speed,control_hz}` with the Radix-Slider `max_speed`.
- **Step 2 — run:** `pnpm test` → Expected: FAIL.
- **Step 3 — implement:** `Autonomy.tsx` (task picker + free-text prompt, `max_speed` Radix Slider, `control_hz` input, Start/Stop) wired to `/api/autonomy`; the store consuming the shared telemetry stream.
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** vitest green; `TASK_PROMPTS` parity proven.

### T12.3.4 — Policy-link charting + drop-to-stop reflection
- **Files:** create `app/src/components/PolicyLinkChart.tsx`, `app/src/lib/series.ts`; modify `app/src/screens/Autonomy.tsx`; test `app/src/lib/series.test.ts`.
- **Step 1 — failing test:** `series.push(sample)` accumulates `last_inference_ms` with a bounded window + downsampling; a staleness banner activates when `chunk_age_ms` crosses the threshold and clears when fresh chunks resume.
- **Step 2 — run:** `pnpm test` → Expected: FAIL.
- **Step 3 — implement:** the bounded series + the chart (Recharts/uPlot) + the staleness banner reflecting drop-to-stop.
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** vitest green.

### T12.3.5 — Policy-server UI (start/stop/health + checkpoint pick)
- **Files:** create `app/src/stores/policyServerStore.ts`, `app/src/components/PolicyServerPanel.tsx`; modify `app/src/screens/Autonomy.tsx`, `app/src-tauri/src/commands.rs` (`pick_path` for a checkpoint dir); test `app/src/stores/policyServerStore.test.ts`.
- **Step 1 — failing test:** `policyServerStore` reflects `PolicyServerState`; Start posts `{checkpoint}`; a checkpoint chosen via the native dialog (`pick_path`) is sent to `/api/policy-server`; health/latency render.
- **Step 2 — run:** `pnpm test` → Expected: FAIL.
- **Step 3 — implement:** the panel + store + the Rust `pick_path` command (directory picker).
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** vitest green; `pick_path` returns a dir to the store.

### T12.3.6 — Integration: closed-loop autonomy round-trip (fake policy, real gate)
- **Files:** create `tests/integration/test_mc_autonomy_live.py` (host-marked).
- **Step 1 — failing test:** against a real `pibotd` (responder transport) + the SPEC-2 **fake websocket policy** (canned action chunks) + a fake camera broker, drive an autonomy session **through `/api/autonomy`**: start → the policy's actions actuate **through the safety gate** → stop; assert the policy-link telemetry surfaces (`connected`, `last_inference_ms`, `chunk_age_ms`); assert a stalled fake policy → drop-to-stop.
- **Step 2 — run:** `pytest tests/integration/test_mc_autonomy_live.py` → Expected: FAIL.
- **Step 3 — implement:** wire the test harness (reuse SPEC-2's fake policy + `tests/test_autonomy_*` patterns); no new product code unless a seam is missing.
- **Step 4 — run:** `pytest tests/integration/test_mc_autonomy_live.py` → Expected: PASS (host-marked; deselected in CI).
- **Done when:** the round-trip passes through the real safety gate with policy-link telemetry visible.

## Milestone acceptance criteria (SPEC-3 M12.3)
UI start/stop of closed-loop autonomy; live policy-link charts that reflect drop-to-stop;
the policy server starts/stops/health-checks from the GUI and serves a chosen checkpoint.

## Risks
- **`serve_policy.py` argv drift** vs the openpi version in `resources/openpi` → build argv from the runbook command and assert it in a test; keep the serve command in one place.
- **Subprocess orphans / zombies** → spawn in a process group; `DELETE` terminates then kills on timeout; tested with the fake server.
- **Policy host swap (OQ-9)** is out of V1 scope → manager interface takes `host`/`port` so a later SSH-backed remote manager can implement the same contract.

## Definition of done
Gates green; autonomy + policy-server management work from the GUI; the host-marked closed-loop
integration passes through the real gate; branch `m12-3-autonomy-policy-server` ready to commit
(ask first).
