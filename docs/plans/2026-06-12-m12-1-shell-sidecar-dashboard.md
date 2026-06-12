# Plan — M12.1: Shell + Sidecar + Connect + Dashboard

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. Note adjacent issues as TODOs; do NOT fix them.

**Goal:** A launchable Tauri desktop app that supervises a bundled Python control-plane sidecar, connects to a real `pibotd` over Nebula, and renders live telemetry.
**Architecture:** Tauri v2 Rust core (shell + sidecar supervisor + token broker) → bundled `pibot/mc` aiohttp sidecar (loopback API, reuses `AgentClient`/`config`/`inventory`) → React webview (Radix/Tailwind/Zustand) Dashboard. The robot link is the unchanged `pibotd` HTTP/WS over Nebula.
**Tech Stack:** Tauri v2 (Rust), pnpm + Vite + React + TypeScript + Radix + Tailwind + Zustand + Vitest; Python 3.11 (aiohttp) for `pibot/mc`; PyInstaller for packaging.
**Practices:** TDD (failing test first) + typed-first + contract-first.
**Required skills:** none (no Claude Code plugin/MCP/agent/hook surface).

| | |
|---|---|
| **Spec** | [SPEC-3](../specs/SPEC-3-pibot-mission-control.md) §3.1–3.4, FR-1…FR-5, §4.1 P1, §5 M12.1 |
| **Phase** | P1 (foundation) |
| **Depends on** | SPEC-1/2 (shipped) — `pibotd`, `AgentClient`, `config`, `inventory` |
| **Branch** | `m12-1-shell-sidecar-dashboard` |
| **Date** | 2026-06-12 |
| **Status** | Not started |

## In scope
The `app/` monorepo scaffold; the Tauri shell + sidecar supervisor + per-launch token; the
`pibot/mc` sidecar skeleton with the loopback API (health, robots, config, connect, telemetry
relay); the Dashboard screen with live telemetry + threshold alerts; PyInstaller packaging +
gate/CI wiring.

## Out of scope
Teleop, video, e-stop failsafe wiring (M12.2); autonomy/policy server (M12.3); data/metrics
(M12.4); provisioning (M12.5). Any change to `pibotd`'s existing endpoints.

## Prerequisites
- A reachable `pibotd` (real Pi over Nebula **or** a local `python -m agent` on a responder/loopback transport) with a valid `agent.token`, for the connect/telemetry tasks.
- `pnpm`, the Rust toolchain (`cargo`), and the Tauri v2 prerequisites installed on the M4 Max.

## Contracts (define first — contract-first)
```ts
// app/src/lib/api/types.ts — the local control-plane envelope the webview consumes.
export interface Health { ok: boolean; version: string; connected: boolean; robot: string | null }
export interface RobotEntry { alias: string; address: string; user: string | null; transport: string }
// Telemetry relay frame == the pibotd snapshot (SPEC-3 Appendix B), re-exported verbatim:
export interface Snapshot {
  ts: number
  pi: { temp_c?: number; throttled?: { currently: string[] }; load?: number[]; mem?: Record<string, number> }
  robot: Record<string, unknown>
  transport: { open?: boolean; kind?: string }
  safety: { estop: boolean }
  policy: { connected: boolean | null; last_inference_ms: number | null; chunk_age_ms: number | null }
}
```
```python
# pibot/mc/types.py — typed sidecar envelopes (mypy-strict), mirrors the TS above.
from typing import TypedDict
class HealthOut(TypedDict): ok: bool; version: str; connected: bool; robot: str | None
class ConnectIn(TypedDict): robot: str
```

## Tasks

### T12.1.1 — Scaffold the `app/` monorepo (pnpm + Vite + React + Tailwind + Radix + Zustand)
- **Files:** create `app/package.json`, `app/pnpm-lock.yaml`, `app/vite.config.ts`, `app/tsconfig.json`, `app/tailwind.config.ts`, `app/postcss.config.js`, `app/.eslintrc.cjs`, `app/index.html`, `app/src/main.tsx`, `app/src/App.tsx`, `app/src/styles.css`; test `app/src/App.test.tsx`; update root `.gitignore` (add `app/node_modules`, `app/dist`, `app/src-tauri/target`).
- **Step 1 — failing test:** Vitest renders `<App/>` and asserts a top bar with a connection indicator and an always-visible **E-STOP** button exist (`screen.getByRole('button', {name: /e-?stop/i})`).
- **Step 2 — run:** `cd app && pnpm install && pnpm test` → Expected: FAIL (no `App`).
- **Step 3 — implement:** minimal `App.tsx` (top bar + e-stop button placeholder + a `<Dashboard/>` slot), Tailwind wired, Radix `Toast`/`Tooltip` providers mounted.
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** `pnpm lint && pnpm typecheck && pnpm test` green.

### T12.1.2 — Tauri v2 shell: sidecar supervisor + per-launch token broker
- **Files:** create `app/src-tauri/Cargo.toml`, `app/src-tauri/tauri.conf.json`, `app/src-tauri/build.rs`, `app/src-tauri/src/main.rs`, `app/src-tauri/src/supervisor.rs`, `app/src-tauri/src/token.rs`, `app/src-tauri/src/commands.rs`; tests inline (`#[cfg(test)]`).
- **Step 1 — failing test (Rust):** `token::generate()` returns a 32-byte URL-safe token, unique across calls; `supervisor::Supervisor` spawns a fake binary (a shell `echo`/sleep script passed via env), reports `Running`, restarts it with backoff after a killed PID, and kills it on `drop`.
- **Step 2 — run:** `cd app/src-tauri && cargo test` → Expected: FAIL.
- **Step 3 — implement:** `Supervisor` (spawn `externalBin` with `--port 0 --token <t>` + token via env `PIBOT_MC_TOKEN`; health-probe `GET /api/health`; exponential backoff restart; `kill_on_drop`); commands `mc_endpoint() -> {url, token}`, `sidecar_status()`; register single-instance + dialog plugins.
- **Step 4 — run:** `cargo fmt --check && cargo clippy -- -D warnings && cargo test` → Expected: PASS.
- **Done when:** Rust gate green; `pnpm tauri build` produces a launchable `.app` (smoke — sidecar may be a stub binary until T12.1.3).

### T12.1.3 — `pibot/mc` sidecar skeleton: loopback API + auth + health (contract-first, typed-first)
- **Files:** create `pibot/mc/__init__.py`, `pibot/mc/__main__.py`, `pibot/mc/types.py`, `pibot/mc/auth.py`, `pibot/mc/app.py`, `pibot/mc/server.py`; test `tests/test_mc_app.py`.
- **Step 1 — failing test:** `create_mc_app(token="t")` → `GET /api/health` returns `{ok, version, connected:false, robot:null}`; the auth middleware **rejects** a request with a missing/incorrect `Authorization: Bearer` (401) and one from a **non-loopback** remote; the server binds `127.0.0.1` only (assert the chosen host).
- **Step 2 — run:** `pytest tests/test_mc_app.py` → Expected: FAIL.
- **Step 3 — implement:** aiohttp app mirroring `agent/app.py`'s middleware shape (reuse `agent.auth.token_ok` / `is_loopback`); `__main__` parses `--port`/`--token` (or `PIBOT_MC_TOKEN`), binds loopback, prints the chosen port on stdout (the Rust supervisor reads it); `types.py` envelopes.
- **Step 4 — run:** `pytest tests/test_mc_app.py && mypy pibot/mc && ruff check pibot/mc` → Expected: PASS.
- **Done when:** Python gate green over `pibot/mc`.

### T12.1.4 — Inventory + config endpoints (reuse `pibot.inventory` / `pibot.config`)
- **Files:** create `pibot/mc/routes_inventory.py`, `pibot/mc/routes_config.py`; modify `pibot/mc/app.py` (register routes); test `tests/test_mc_inventory_config.py`.
- **Step 1 — failing test:** against a temp `$PIBOT_CONFIG_DIR`, `GET/POST/DELETE /api/robots` add→list→alias→rm round-trips through `pibot.inventory.Inventory`; `POST /api/config` **rejects an unknown key and a wrong-typed value** with the same error class as `pibot.config.load_config` (mirror `tests/test_config.py` cases); `GET /api/config` returns the resolved config.
- **Step 2 — run:** `pytest tests/test_mc_inventory_config.py` → Expected: FAIL.
- **Step 3 — implement:** thin handlers delegating to `Inventory` and `load_config`/validation (no re-implementation of the rules — call the existing validator).
- **Step 4 — run:** `pytest tests/test_mc_inventory_config.py && mypy pibot/mc` → Expected: PASS.
- **Done when:** green; unknown-key/wrong-type parity proven.

### T12.1.5 — Robot-link manager: connect/disconnect + telemetry relay + endpoint cache push
- **Files:** create `pibot/mc/robot_link.py`, `pibot/mc/routes_link.py`; modify `pibot/mc/app.py`; test `tests/test_mc_robot_link.py`; integration `tests/integration/test_mc_live.py`.
- **Step 1 — failing test:** against a **fake `pibotd`** (an aiohttp test server exposing `/telemetry` WS + bearer auth, reusing `tests/helpers.py` patterns), `POST /api/connect{robot}` opens an `AgentClient`, `WS /api/telemetry` relays a snapshot frame unchanged, `POST /api/disconnect` closes it; on connect the manager calls a **cache-endpoint hook** with `{url, token}` (assert via a fake bridge — this is the M12.2 e-stop failsafe seam, wired now).
- **Step 2 — run:** `pytest tests/test_mc_robot_link.py` → Expected: FAIL.
- **Step 3 — implement:** `RobotLink` wrapping `AgentClient` (resolve address via `Inventory`, load token via `agent.auth.load_token`); `WS /api/telemetry` pump from `AgentClient.telemetry_stream()`; an injectable `on_connect(url, token)` callback (the Rust `cache_robot_endpoint` bridge in M12.2; a no-op default here).
- **Step 4 — run:** `pytest tests/test_mc_robot_link.py` → Expected: PASS. Then the host-marked integration test against a real `python -m agent` on the responder transport.
- **Done when:** unit green; `tests/integration/test_mc_live.py` passes against a real `pibotd` (host-marked, deselected in CI).

### T12.1.6 — Dashboard screen: live telemetry + threshold alerts (Zustand)
- **Files:** create `app/src/stores/connectionStore.ts`, `app/src/stores/telemetryStore.ts`, `app/src/lib/alerts.ts`, `app/src/screens/Dashboard.tsx`, `app/src/lib/api/client.ts`; tests `app/src/stores/telemetryStore.test.ts`, `app/src/lib/alerts.test.ts`.
- **Step 1 — failing test:** `telemetryStore` ingests a `Snapshot` and exposes the latest values; `alerts(snapshot)` returns alert strings for hot SoC / throttle / low battery / transport-down / e-stop / stale-policy — **the same cases as `pibot/monitor.check_thresholds`** (port its thresholds: `temp ≥ 80`, `battery < 11`, `policy chunk_age > 1000ms`).
- **Step 2 — run:** `pnpm test` → Expected: FAIL.
- **Step 3 — implement:** the stores (Zustand) + `alerts.ts` mirroring `check_thresholds`; `Dashboard.tsx` renders pi/robot/transport/safety/policy with Radix components and an alerts banner; `client.ts` opens `WS /api/telemetry` using `mc_endpoint()`.
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** vitest green; the alert cases match `check_thresholds` one-for-one.

### T12.1.7 — Packaging (PyInstaller externalBin) + gate/CI wiring
- **Files:** create `app/src-tauri/bin/` (externalBin target), `app/scripts/build-sidecar.sh` (PyInstaller one-folder of `pibot.mc`); modify `app/src-tauri/tauri.conf.json` (externalBin + resources), `scripts/check.sh` (run the Python gate over `pibot/mc` + invoke the frontend gate), `.github/workflows/ci.yml` (frontend job + `pibot/mc`); test `tests/test_ci_workflow.py` (extend), `tests/test_mc_packaging.py`.
- **Step 1 — failing test:** `tests/test_ci_workflow.py` asserts `ci.yml` has a frontend job running `pnpm lint/typecheck/test` and a `tauri build` smoke, and that the Python job covers `pibot/mc`; `tests/test_mc_packaging.py` builds the sidecar (host-marked) and asserts the produced binary answers `GET /api/health` on a loopback port.
- **Step 2 — run:** `pytest tests/test_ci_workflow.py` → Expected: FAIL.
- **Step 3 — implement:** the PyInstaller build script (resolves OQ-4), the `externalBin` wiring, the extended `scripts/check.sh` and `ci.yml`.
- **Step 4 — run:** `bash scripts/check.sh` → Expected: PASS; `pnpm tauri build` → launchable `.app`.
- **Done when:** the full gate green; a built `.app` launches, the supervised sidecar comes up, and the Dashboard shows live telemetry from a real `pibotd` (manual verify — the automated E2E harness lands in M12.2).

## Milestone acceptance criteria (SPEC-3 M12.1)
Launchable `.app`; supervised sidecar with observed auto-restart; connect to a real `pibotd`
and render a streaming telemetry dashboard with threshold alerts matching `check_thresholds`.

## Risks
- **Sidecar packaging fragility** (R-1) → if PyInstaller is flaky, fall back to a pinned bundled venv shipped as a resource; keep the `externalBin` contract identical.
- **Tauri v2 + Python lifecycle on macOS** (R-7) → the supervisor owns spawn/kill via a process group + `kill_on_drop`; single-instance plugin prevents orphans; tested with a fake binary.

## Definition of done
Python + frontend + Rust gates green; a built `.app` connects and streams telemetry; sidecar
auto-restart proven; branch `m12-1-shell-sidecar-dashboard` ready to commit (ask first).
