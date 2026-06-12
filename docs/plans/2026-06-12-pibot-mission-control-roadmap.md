# Plan Roadmap — PiBot Mission Control (SPEC-3)

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement each milestone plan task-by-task.
> **Scope guard:** Do ONLY what each milestone file lists. Note adjacent issues as TODOs; do NOT fix them.

| | |
|---|---|
| **Source spec** | [SPEC-3 — PiBot Mission Control](../specs/SPEC-3-pibot-mission-control.md) |
| **Created** | 2026-06-12 |
| **Plan set** | One file per milestone, **M12.1 → M12.5** (SPEC-3 build phases P1–P5) |
| **Status** | Not started |
| **Delivery** | **One comprehensive V1 release** (SPEC-3 Decision D-4): the milestones are the internal engineering sequence; the app ships once, at the M12.5 release gate. |

This roadmap indexes the five milestone plans for SPEC-3. Each milestone file is
self-contained and executable on its own (via `/lore:continue` or `/lore:execute`),
but they share the conventions below — **read this once, then the per-milestone file.**

## Milestone index

| # | Phase | Plan file | Delivers | Depends on |
|---|---|---|---|---|
| M12.1 | P1 | [m12-1-shell-sidecar-dashboard](2026-06-12-m12-1-shell-sidecar-dashboard.md) | Tauri shell + supervised Python sidecar + connect + live telemetry dashboard | SPEC-1/2 (done) |
| M12.2 | P2 | [m12-2-teleop-estop-video](2026-06-12-m12-2-teleop-estop-video.md) | `pibotd WS /video` + camera broker · teleop (kbd+gamepad) · always-on e-stop · live video · safety-bypass test | M12.1 |
| M12.3 | P3 | [m12-3-autonomy-policy-server](2026-06-12-m12-3-autonomy-policy-server.md) | Autonomy session control + live policy-link charts + openpi policy-server management | M12.2 |
| M12.4 | P4 | [m12-4-data-metrics-sessions](2026-06-12-m12-4-data-metrics-sessions.md) | Demonstration record/browse · fine-tune tracking · persisted metrics time-series + charts + export · session record/replay | M12.3 |
| M12.5 | P5 | [m12-5-provisioning-hardening-release](2026-06-12-m12-5-provisioning-hardening-release.md) | GUI-wrapped flash/deploy/firmware/eeprom with guards · notifications · security/E2E hardening · **V1 release gate** | M12.4 |

> **Single-ship reminder:** M12.1–M12.5 are not five separate releases. They are runnable,
> reviewable checkpoints toward **one** V1 release at M12.5 (SPEC-3 §4.1, Decision D-4). Each
> checkpoint is dogfoodable; the CLI remains the fallback for anything the GUI doesn't yet cover.

## Dependency graph
```text
SPEC-1 (M0–M6, done) ─┐
SPEC-2 (M7–M11, done) ─┴─► M12.1 ─► M12.2 ─► M12.3 ─► M12.4 ─► M12.5
                           shell    live ops   autonomy  data +    ops +
                           +tlm     +video     +policy   metrics   RELEASE
                                    (NEW pibotd /video)
```

## Shared conventions (apply to every task in every milestone)

### Development discipline — strict TDD + typed-first + contract-first
Every task follows **red → green → refactor**:
1. Write the failing test(s) first; run them; confirm they fail for the right reason.
2. Write the minimal implementation to pass.
3. Refactor with tests green.

Additionally (Phase 2 answers):
- **Typed-first** — define the types/schemas before the logic: mypy-strict Python dataclasses/`TypedDict` for the sidecar, TypeScript interfaces for the local-API / telemetry / video shapes, Rust types for the Tauri command bridge.
- **Contract-first** — pin the **local control-plane HTTP/WS contract** and the new **`pibotd WS /video` frame contract** (SPEC-3 Appendix B) before implementing either side, so the frontend and the sidecar build against a fixed seam.

I/O paths (the `pibotd` link, the policy subprocess, the camera, disk/bootloader ops) are
tested against **fakes, loopbacks (the responder transport / aiohttp test servers), and the
documented Arduino-echo stand** — never by skipping the test. Real-hardware/E2E is additive.

### Quality gates — definition of done for every task
A task is not done until **all** of these pass.

**Python (`pibot`, `agent`, the new `pibot/mc`):**
- `ruff check .` — zero lint errors
- `ruff format --check .` — formatting clean
- `mypy pibot agent` — zero type errors (strict-ish; `pyproject.toml`)
- `pytest` — green, coverage ≥ 80 % on logic modules
- No stubs/TODO/placeholder (repo rule); `--json` on read commands; `--dry-run` on state-changing commands

**Frontend (`app/`, the new Tauri+React surface):**
- `pnpm lint` (ESLint) + `pnpm typecheck` (`tsc --noEmit`) — clean
- `pnpm test` (Vitest) — green
- `cargo fmt --check` + `cargo clippy -- -D warnings` + `cargo test` in `app/src-tauri` — clean
- `pnpm tauri build` — produces a launchable macOS `.app` (smoke)

**The local gate** (`bash scripts/check.sh`) is extended in M12.1 to run the Python gate over
`pibot/mc` and to invoke the frontend gate; CI (`.github/workflows/ci.yml`, asserted by
`tests/test_ci_workflow.py`) is extended to match. Hardware/model/E2E paths stay deselected by
default (host/hardware-marked), exactly as SPEC-1/2.

### Release-blocking safety regressions (carry across milestones)
These tests gate the V1 release and must never be weakened (SPEC-3 FR-8/FR-19/FR-26):
- **Safety-bypass** (M12.2): no GUI-issued motion reaches the motors except through `pibotd`'s gate; a GUI command is clamped/rejected exactly as a teleop command; link-stall → drop-to-stop.
- **E-stop under loss** (M12.2): e-stop latches the robot even with the telemetry/control/video sockets killed **and with the sidecar process killed** (Rust core uses the cached robot endpoint).
- **Destructive-guard** (M12.5): 0 GUI executions of a disk/bootloader write without the modal confirm + wrong-disk guard passing.
- **Secrets-never-committed** (M12.5): the M6 invariant test, extended to `pibot/mc` + app config + the per-launch token.

### Conventions
- **Branch per milestone:** `m12-1-shell-sidecar-dashboard`, `m12-2-teleop-estop-video`, `m12-3-autonomy-policy-server`, `m12-4-data-metrics-sessions`, `m12-5-provisioning-hardening-release`.
- **Desktop app home:** `app/` (monorepo alongside the Python suite) — resolves SPEC-3 OQ-10.
- **Sidecar packaging:** PyInstaller one-folder shipped as a Tauri `externalBin` — resolves SPEC-3 OQ-4 (fallback: a pinned bundled venv if PyInstaller proves fragile — R-1).
- **App state dir:** `~/Library/Application Support/PiBotMissionControl/` (SQLite metrics/session store) — resolves SPEC-3 OQ-7; retention caps set in M12.4.
- **Commit only when asked** (repo rule); ask before committing a finished branch.

## Traceability (milestone → SPEC-3 requirements)
| Milestone | SPEC-3 FRs covered |
|---|---|
| M12.1 | FR-1, FR-2, FR-3, FR-4, FR-5 |
| M12.2 | FR-6, FR-7, FR-8, FR-9, FR-10, FR-26 (safety invariants) |
| M12.3 | FR-11, FR-12, FR-13 |
| M12.4 | FR-14, FR-15, FR-16, FR-17, FR-20, FR-21 |
| M12.5 | FR-18, FR-19, FR-22, FR-25/FR-26 (invariants), release gate |
