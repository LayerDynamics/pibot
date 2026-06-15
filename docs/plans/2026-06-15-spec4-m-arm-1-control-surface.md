# Plan — M-ARM-1: Motion control surface (SPEC-4)

> **Status: ✅ Shipped (2026-06-15).** All tasks 1.1–1.7 complete; `scripts/check.sh` + the desktop
> gate green. New host arm safety gate (`pibot/arm/safety.py`), agent `WS /arm/control`,
> `AgentClient`/`RobotLink` motion methods, MC `POST /api/arm/*` routes, `pibot arm` CLI, and `Arm.tsx`
> controls. Runbook: [`docs/runbooks/arm-operation.md`](../runbooks/arm-operation.md).
>
> **For Claude:** execute with `lore:execute`. **TDD mandatory** (write the failing test first → watch
> it fail → implement → `scripts/check.sh` green). Shared decisions, discipline, and invariants live in
> the [plan index](./2026-06-15-spec4-robot-arm-implementation.md). **Ask before any `git` commit.**

## Goal

Expose PiBot's already-built joint-motion engine end-to-end — agent write channel, host safety gate,
client/RobotLink methods, `pibot arm` CLI, and Arm-screen controls. **No new motion math**: the
firmware verbs and `ArmManager.jpos/jvel/jstop/home/estop/enable/move_synchronized` already exist and
are unit-tested; this milestone wires them up.

## Realizes

- SPEC-4 **FR-1..FR-6**; closes `OtherArms.md` **§6B-1** (control surface unwired) and the **§6A**
  "motion UI" deferral.

## Depends on / blocks

- **Depends on:** the shipped baseline (firmware safety, `ArmManager`, telemetry path). No hardware
  blank required.
- **Blocks:** M-ARM-2 (gripper rides this surface) and M-ARM-5 (programs drive motion through it).

## Tasks

### 1.1 — Host arm safety gate

- **What:** new `pibot/arm/safety.py` with pure validators — joint-id range, angle clamp to per-joint
  `[min_deg,max_deg]`, velocity clamp to `max_dps`, **homing-required-before-jpos**, and
  **e-stop-latched refusal**. Add an `arm_joint_limits` field (parallel per-logical-joint
  `{min_deg,max_deg,max_dps}`) to `pibot/config.py` (alongside `arm_serial_ports` /
  `arm_joints_per_board`).
- **Files:** `pibot/arm/safety.py` (new), `pibot/config.py`.
- **Test-first:** `tests/test_arm_safety.py` — accept in-range; clamp over-range angle/velocity; reject
  `jpos` when unhomed; reject all motion when e-stop latched; per-joint limit lookup.
- **Done when:** the gate's accept/clamp/reject behavior is fully covered and `scripts/check.sh` green.

### 1.2 — Agent `/arm/control` WebSocket

- **What:** in `agent/app.py`, a WS handler at `/arm/control` accepting frames `{cmd, joint?, deg?,
  dps?, seconds?, targets?, on?}` for `jpos/jmove/jvel/jstop/home/move/enable/estop/clear_estop`. Route
  every frame through the gate (1.1) → `ArmManager` via `asyncio.to_thread` (sends only — `_arm_drain`
  remains the sole `recv` reader). Maintain latched-e-stop state + per-joint homed (sourced from the
  telemetry cache). Reply `{type:"ack"}` / `{type:"nak", reason}`. Bearer-token auth like other routes.
- **Files:** `agent/app.py`.
- **Test-first:** extend `tests/test_agent_arm.py` (loopback/responder) — jog → ack; `jpos` while
  unhomed → nak; `estop` latches then subsequent motion → nak until `clear_estop`; no-arm-configured →
  clean error (not a crash).
- **Done when:** WS round-trips through the gate to `ArmManager`; safety refusals verified; gate green.

### 1.3 — Client + RobotLink methods

- **What:** add `arm_jog`, `arm_move_joint`, `arm_move_joints`, `arm_home`, `arm_estop`,
  `arm_clear_estop`, `arm_enable` to `AgentClient` (`pibot/control/client.py`) and delegate them from
  `RobotLink` (`pibot/mc/robot_link.py`) — preserve the delegation invariant (RobotLink never opens its
  own link).
- **Files:** `pibot/control/client.py`, `pibot/mc/robot_link.py`.
- **Test-first:** extend `tests/test_agent_arm.py` / `tests/test_mc_arm.py` (methods hit the right
  frames; RobotLink delegates to AgentClient).
- **Done when:** both layers expose the motion methods with passing tests.

### 1.4 — Mission Control motion routes

- **What:** in `pibot/mc/routes_arm.py`, add `POST /api/arm/{jog,move,move-all,home,estop,clear_estop,
  enable}` delegating to `RobotLink` — thin proxy, **no motion logic in MC**.
- **Files:** `pibot/mc/routes_arm.py`.
- **Test-first:** extend `tests/test_mc_arm.py` — each route → RobotLink call; not-connected → 503.
- **Done when:** routes proxy correctly; gate green.

### 1.5 — `pibot arm` CLI

- **What:** in `pibot/cli.py`, add an `arm` subparser: `telemetry`, `jog <joint> <dps>`,
  `move <joint> <deg> [--speed]`, `move-all <j=deg,...> --seconds <s>`, `home [<joint>|--all]`,
  `estop`, `clear`, `enable`, `disable`, `pose <name>`. Honor global `--json`/`--timeout`.
- **Files:** `pibot/cli.py`.
- **Test-first:** `tests/test_cli_arm.py` — arg parsing + dispatch against a fake AgentClient; `--json`
  output shape.
- **Done when:** CLI drives the arm through the agent; gate green.

### 1.6 — Arm-screen controls

- **What:** `app/src/screens/Arm.tsx` + `app/src/stores/armStore.ts` — per-joint jog (±) and home
  buttons, a go-to-angle field, an always-visible **E-Stop** (latches) + clear, enable/disable, and a
  per-joint homed indicator. `armStore` gains action thunks (it is currently read-only); jog is disabled
  while e-stop is latched.
- **Files:** `app/src/screens/Arm.tsx`, `app/src/stores/armStore.ts`.
- **Test-first:** extend `app/src/stores/armStore.test.ts` — motion actions POST to the right endpoints;
  latched e-stop disables jog; plus an Arm-render test for the controls.
- **Done when:** controls work against the MC routes; desktop gate (vitest + tsc + eslint) green.

### 1.7 — Docs

- **What:** new `docs/runbooks/arm-operation.md` (home → jog → pose → e-stop, and e-stop recovery); mark
  `OtherArms.md` §6B-1 shipped; add `/arm/control` to `CLAUDE.md`'s agent-endpoint list and `pibot arm`
  to its CLI subcommand list.
- **Files:** `docs/runbooks/arm-operation.md` (new), `docs/research/stepper-robot-arms-github/OtherArms.md`,
  `CLAUDE.md`.
- **Done when:** docs reflect the shipped surface (NFR-8).

## Milestone DoD

Jog / home / move / e-stop all work from the **CLI** and the **Arm screen** through the host safety
gate; safety regression tests (unhomed-refusal, latched-e-stop) green; `scripts/check.sh` + desktop
gate green. No commit without the user's go-ahead.

## Notes / risks

- Sends and the `_arm_drain` receive loop must not contend on the transport — keep `_arm_drain` the sole
  reader; motion sends go through `to_thread` and never call `recv`.
- E-stop must remain reachable independent of any later IK/trajectory code (NFR-1) — the WS `estop`
  handler routes straight to `ArmManager.estop` without passing through solver code.
