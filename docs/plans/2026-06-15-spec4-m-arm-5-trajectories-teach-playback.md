# Plan — M-ARM-5: Trajectories + teach/playback (SPEC-4)

> **For Claude:** execute with `lore:execute`. **TDD mandatory** (failing test first → implement →
> `scripts/check.sh` green). Shared decisions/discipline/invariants: see the
> [plan index](./2026-06-15-spec4-robot-arm-implementation.md). **Ask before any `git` commit.**

## Goal

Add coordinated trajectories beyond synchronized arrival (trapezoidal joint ramps + Cartesian-linear
with SLERP), and a teach/playback system with on-Pi persistence — record poses, build ordered programs
(move-J / move-L / grip / tool / wait / loop), and replay them through the safety gate, abortable by
e-stop.

## Realizes

- SPEC-4 **FR-15, FR-16, FR-17**; closes `OtherArms.md` **§6A** plan phase **A.4** (trajectories) and
  **§6B-3** (teach/playback + persistence).

## Depends on / blocks

- **Depends on:** M-ARM-1 (programs drive motion through the surface); M-ARM-4 (Cartesian-linear paths
  need IK). Joint-space trajectories + teach/playback can land before M-ARM-4; Cartesian (move-L) steps
  require it.
- **Blocks:** nothing downstream.

## Tasks

### 5.1 — Trajectory generator

- **What:** new `pibot/arm/trajectory.py` — trapezoidal joint-space ramps and Cartesian-linear paths
  with **SLERP** orientation, producing timed `(targets, dt)` frames. Joint-space generation is
  pure-stdlib; Cartesian generation calls FK/IK (M-ARM-3/4) only when invoked (kept lazy).
- **Files:** `pibot/arm/trajectory.py`.
- **Test-first:** `tests/test_arm_trajectory.py` — ramp is monotonic and velocity-bounded; endpoints
  exact; `dt` spacing correct; Cartesian path waypoints interpolate position + orientation.
- **Done when:** generator output is correct and bounded; gate green.

### 5.2 — Trajectory executor

- **What:** add `ArmManager.run_trajectory(frames, abort_check)` — pace timed `jmove` frames, checking
  `abort_check()` before each frame so e-stop/stop halts mid-trajectory.
- **Files:** `pibot/arm/manager.py`.
- **Test-first:** extend `tests/test_arm_manager.py` — frames sent in order at the right cadence; abort
  stops early and holds.
- **Done when:** executor streams + aborts correctly; gate green.

### 5.3 — Pose / program model

- **What:** new `pibot/arm/programs.py` — `Pose` and `Program` dataclasses, JSON (de)serialization,
  **record-from-telemetry** (snapshot current joints → named pose), step kinds
  `moveJ|moveL|grip|tool|wait|loop`, and validation.
- **Files:** `pibot/arm/programs.py`.
- **Test-first:** `tests/test_arm_programs.py` — JSON round-trip; record from a telemetry snapshot;
  malformed program rejected; loop/wait semantics.
- **Done when:** model serializes + validates; gate green.

### 5.4 — Agent persistence + runner

- **What:** in `agent/app.py`, add `GET/POST/DELETE /arm/poses[/{name}]` and
  `/arm/programs[/{name}]` persisted as JSON under the agent state dir; `POST /arm/programs/{name}/run`
  (a cancellable asyncio task that drives each step through the host gate + trajectory executor) and
  `POST /arm/programs/stop`. **E-stop aborts a running program.**
- **Files:** `agent/app.py`.
- **Test-first:** extend `tests/test_agent_arm.py` — pose/program CRUD; run executes steps in order;
  e-stop aborts mid-run; persistence survives an agent restart; runner never blocks the event loop.
- **Done when:** programs persist, run, and abort correctly; gate green.

### 5.5 — Client / RobotLink / MC

- **What:** add pose+program methods to `AgentClient`/`RobotLink` and `…/poses`, `…/programs`,
  `…/programs/{name}/run`, `…/programs/stop` proxy routes in `pibot/mc/routes_arm.py`.
- **Files:** `pibot/control/client.py`, `pibot/mc/robot_link.py`, `pibot/mc/routes_arm.py`.
- **Test-first:** extend `tests/test_mc_arm.py`.
- **Done when:** MC proxies pose/program CRUD + run/stop; gate green.

### 5.6 — CLI

- **What:** add `pibot arm {pose-save,pose-list,program-run,program-list,program-stop}`.
- **Files:** `pibot/cli.py`.
- **Test-first:** extend `tests/test_cli_arm.py`.
- **Done when:** CLI manages + runs programs; gate green.

### 5.7 — UI program panel

- **What:** `app/src/screens/Arm.tsx` + `app/src/stores/armStore.ts` — record current pose, build/edit
  an ordered step list, run/stop with per-step progress.
- **Files:** `app/src/screens/Arm.tsx`, `app/src/stores/armStore.ts`.
- **Test-first:** extend `app/src/stores/armStore.test.ts` — program CRUD + run/stop actions; abort
  surfaces.
- **Done when:** program panel works against the MC routes; desktop gate green.

### 5.8 — Docs

- **What:** mark `OtherArms.md` §6B-3 + §6A(A.4) shipped; extend `docs/runbooks/arm-operation.md` with
  teach/playback.
- **Files:** `docs/research/stepper-robot-arms-github/OtherArms.md`, `docs/runbooks/arm-operation.md`.
- **Done when:** docs accurate (NFR-8).

## Milestone DoD

Record → name → program → replay with on-Pi JSON persistence; playback abortable by e-stop;
trapezoidal joint ramps + Cartesian-linear paths working; `scripts/check.sh` + desktop gate green.

## Notes / risks

- **Runner must not block the event loop (SPEC R7):** the program runner is a cancellable async task;
  `ArmManager` calls go through `to_thread`; e-stop preempts the runner.
- Persistence path lives under the agent state dir on the Pi (SPEC OQ-6 default); document the location.
- move-L steps require M-ARM-4 — if M-ARM-5 lands first, gate move-L behind an "IK unavailable" message.
