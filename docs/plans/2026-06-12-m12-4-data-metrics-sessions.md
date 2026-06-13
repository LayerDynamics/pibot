# Plan — M12.4: Data & Models + Metrics + Sessions

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. Note adjacent issues as TODOs; do NOT fix them.

**Goal:** Record and review demonstration data, track fine-tune runs/served checkpoints, and persist complete telemetry/metrics as a queryable, exportable time-series with replayable sessions.
**Architecture:** A local SQLite store (under the app state dir) holds the telemetry time-series, session recordings, fine-tune runs, and ops-job rows; the telemetry fan-out (M12.1) feeds the metrics + session recorders; demonstration recording reuses the SPEC-2 `EpisodeLogger`/dataset path; the Data screen browses the LeRobot dataset read-only.
**Tech Stack:** Python `sqlite3` (stdlib), aiohttp (sidecar), SPEC-2 `pibot/ml/{episode_logger,record,dataset}.py`, React/Zustand + a charting lib.
**Practices:** TDD + typed-first + contract-first.
**Required skills:** none.

| | |
|---|---|
| **Spec** | [SPEC-3](../specs/SPEC-3-pibot-mission-control.md) FR-14…FR-17, FR-20, FR-21; §3.3 (data model), §3.9; §4.1 P4; §5 M12.4 |
| **Phase** | P4 (data & metrics) |
| **Depends on** | M12.3 (autonomy + telemetry stream in place) |
| **Branch** | `m12-4-data-metrics-sessions` |
| **Date** | 2026-06-12 |
| **Status** | Software complete in the working tree (T12.4.1–T12.4.7; suites green) but **UNCOMMITTED** on branch `m12-2-teleop-estop-video`. Data & Models screen mounted in the App shell (frontend integration, 2026-06-12). |

## In scope
The SQLite metrics time-series (write/query/export/retention); the telemetry→metrics+session
fan-out; the session recorder + replay; demonstration record start/stop (SPEC-2 path); the
LeRobot episode browser; fine-tune-run tracking + serve-checkpoint; the Data & Models screen +
metrics charts/export.

## Out of scope
Provisioning/flash (M12.5); the V1 release gate (M12.5). Persisting raw **video clips** is
deferred (SPEC-3 OQ-3) — this milestone persists telemetry/metrics + session events, not video.

## Prerequisites
- M12.3 done; the telemetry fan-out seam from M12.1 (`RobotLink` distributing snapshots).
- SPEC-2 demonstration path present: `pibot/ml/episode_logger.py`, `pibot/ml/record.py`, `pibot/ml/dataset.py`.
- App state dir chosen: `~/Library/Application Support/PiBotMissionControl/` (SPEC-3 OQ-7).

## Contracts (define first — contract-first)
```python
# pibot/mc/metrics.py — typed-first SQLite schema (one row per telemetry sample).
# table telemetry(ts REAL, robot TEXT, temp_c REAL, battery_v REAL, estop INT,
#                 transport_open INT, policy_connected INT, last_infer_ms REAL, chunk_age_ms REAL, raw JSON)
# table sessions(id TEXT PK, robot TEXT, started REAL, ended REAL, events JSON)
# table finetune_runs(id TEXT PK, dataset TEXT, started REAL, status TEXT, checkpoint_out TEXT, served INT)
# Retention (OQ-7): keep <= MAX_AGE_DAYS=30 and <= MAX_ROWS (size cap); prune oldest beyond caps.
```
```ts
// app/src/lib/api/data.ts
export interface Episode { id: string; task: string; length: number; started: number; ended: number }
export interface FineTuneRun { id: string; dataset: string; status: string; checkpoint_out: string | null; served: boolean }
export interface HistoryQuery { from: number; to: number; fields: string[] }
```

## Tasks

### T12.4.1 — Metrics time-series store (SQLite: write + query + export + retention)
- **Files:** create `pibot/mc/metrics.py`, `pibot/mc/state_dir.py` (resolve `~/Library/Application Support/PiBotMissionControl/`); test `tests/test_mc_metrics.py`.
- **Step 1 — failing test:** writing 1000 samples then `query(from,to,fields)` returns the windowed rows/columns; retention prunes rows beyond `MAX_AGE_DAYS`/`MAX_ROWS` (assert oldest dropped, newest kept); `export(from,to,"csv")` and `"json"` round-trip the same data; the writer is buffered (a batch flush) and does not block the caller.
- **Step 2 — run:** `pytest tests/test_mc_metrics.py` → Expected: FAIL.
- **Step 3 — implement:** `MetricsStore` (SQLite under the state dir; flattened columns + a `raw` JSON; batched writes via a queue; `query`/`export`/`prune`); `state_dir.py` (create on first use).
- **Step 4 — run:** `pytest tests/test_mc_metrics.py && mypy pibot/mc` → Expected: PASS.
- **Done when:** green; retention + export proven.

### T12.4.2 — Telemetry fan-out → metrics; `/api/telemetry/history` + `/export`
- **Files:** modify `pibot/mc/robot_link.py` (fan each snapshot to the metrics recorder), `pibot/mc/app.py`; create `pibot/mc/routes_metrics.py`; test `tests/test_mc_metrics_routes.py`.
- **Step 1 — failing test:** a relayed telemetry stream lands rows in the store; `GET /api/telemetry/history?from&to&fields` returns them; `GET /api/telemetry/export?fmt=csv|json` streams the export; under a 10 Hz feed for N seconds, **≤ 1 %** of samples are missing (loss assertion).
- **Step 2 — run:** `pytest tests/test_mc_metrics_routes.py` → Expected: FAIL.
- **Step 3 — implement:** wire the fan-out (the snapshot already flows to the webview + alerting; add the metrics sink) + the history/export routes.
- **Step 4 — run:** `pytest tests/test_mc_metrics_routes.py` → Expected: PASS.
- **Done when:** green; ≤ 1 % loss at 10 Hz proven.

### T12.4.3 — Session recorder + replay
- **Files:** create `pibot/mc/sessions.py`, `pibot/mc/routes_sessions.py`; modify `pibot/mc/app.py`; test `tests/test_mc_sessions.py`.
- **Step 1 — failing test:** `POST /api/sessions` (start) → record telemetry + control/autonomy/ops **events** → `DELETE`/stop finalizes; `GET /api/sessions` lists them; `GET /api/sessions/{id}` returns a replayable record (ordered events + a telemetry window reference) and an export.
- **Step 2 — run:** `pytest tests/test_mc_sessions.py` → Expected: FAIL.
- **Step 3 — implement:** `SessionRecorder` (bind start→stop; collect events from the sidecar's event bus; reference the metrics window); the routes.
- **Step 4 — run:** `pytest tests/test_mc_sessions.py` → Expected: PASS.
- **Done when:** green; a session replays.

### T12.4.4 — Demonstration recording (`/api/record` → SPEC-2 path)
- **Files:** create `pibot/mc/routes_record.py`; modify `pibot/mc/robot_link.py`; test `tests/test_mc_record.py`.
- **Step 1 — failing test:** `POST /api/record{prompt}` starts a recording tagged with the prompt and invokes the SPEC-2 recorder (`pibot/ml/record.py` / `EpisodeLogger`); a fake step writes a dataset row; `DELETE /api/record` finalizes the episode.
- **Step 2 — run:** `pytest tests/test_mc_record.py` → Expected: FAIL.
- **Step 3 — implement:** delegate to the existing demonstration path (reuse, do not re-implement the dataset writer); thread the prompt tag through.
- **Step 4 — run:** `pytest tests/test_mc_record.py` → Expected: PASS.
- **Done when:** green; a demonstration episode is produced via the SPEC-2 logger.

### T12.4.5 — LeRobot episode browser (`/api/episodes`)
- **Files:** create `pibot/mc/routes_episodes.py`, `pibot/mc/datasets.py` (index, read-only); test `tests/test_mc_episodes.py`.
- **Step 1 — failing test:** against a temp LeRobot dataset (reuse `tests/test_dataset.py` fixtures), `GET /api/episodes` lists episodes with `{id,task,length,started,ended}`; `GET /api/episodes/{id}` returns per-episode metadata and a frame where available; the dataset is **never mutated**.
- **Step 2 — run:** `pytest tests/test_mc_episodes.py` → Expected: FAIL.
- **Step 3 — implement:** a read-only indexer over the dataset (reuse `pibot/ml/dataset.py` readers); the routes.
- **Step 4 — run:** `pytest tests/test_mc_episodes.py` → Expected: PASS.
- **Done when:** green; read-only browse proven.

### T12.4.6 — Fine-tune-run tracking + serve-checkpoint (+ optional launch, SHOULD)
- **Files:** create `pibot/mc/finetune.py`, `pibot/mc/routes_finetune.py`; modify `pibot/mc/policy_server.py` (serve a tracked checkpoint), `pibot/mc/app.py`; test `tests/test_mc_finetune.py`.
- **Step 1 — failing test:** `GET /api/finetune` lists `FineTuneRun` rows; marking a run **served** drives `PolicyServerManager` to serve that `checkpoint_out`; **(SHOULD, FR-17)** `POST /api/finetune` launches a **fake trainer** subprocess and streams its log, updating `status` on exit.
- **Step 2 — run:** `pytest tests/test_mc_finetune.py` → Expected: FAIL.
- **Step 3 — implement:** the run registry (SQLite) + the serve hook into M12.3's manager; the optional launch via an injected `train_cmd` factory (fake in CI; the real command host-marked).
- **Step 4 — run:** `pytest tests/test_mc_finetune.py` → Expected: PASS.
- **Done when:** green; tracking + serve-checkpoint proven; optional launch streams a fake log.

### T12.4.7 — Data & Models screen + Metrics charts/export (webview)
- **Files:** create `app/src/screens/Data.tsx`, `app/src/stores/dataStore.ts`, `app/src/stores/metricsStore.ts`, `app/src/components/{EpisodeList,FineTunePanel,MetricsChart,SessionReplay}.tsx`; tests `app/src/stores/dataStore.test.ts`, `app/src/stores/metricsStore.test.ts`.
- **Step 1 — failing test:** `dataStore` lists episodes + fine-tune runs from the API; `metricsStore` requests a history window and feeds a chart series; export buttons hit `/api/telemetry/export`; the session-replay component steps through a recorded session.
- **Step 2 — run:** `pnpm test` → Expected: FAIL.
- **Step 3 — implement:** the screen + stores + components (Radix layout; the same chart lib as M12.3); CSV/JSON export via a save dialog (`pick_path`).
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** vitest green; browse + charts + export + replay render.

## Milestone acceptance criteria (SPEC-3 M12.4)
Record a demonstration and see it in the dataset browser; 10 Hz metrics persist with ≤ 1 %
loss; CSV/JSON export round-trips; a recorded session replays; fine-tune runs are tracked and a
chosen checkpoint can be served.

## Risks
- **Metrics store growth** (R-8) → retention caps (age + size) enforced in T12.4.1; a "clear history" action; buffered writes never block telemetry.
- **Reusing the SPEC-2 dataset path** must stay read-only for browse → the indexer never writes; recording goes only through the existing `EpisodeLogger`.
- **Fine-tune launch is heavy** → kept SHOULD (FR-17) and behind an injected command; CI uses a fake trainer only.

## Definition of done
Gates green; data record/browse, metrics persistence + charts + export, session replay, and
fine-tune tracking/serve all work; branch `m12-4-data-metrics-sessions` ready to commit (ask first).
