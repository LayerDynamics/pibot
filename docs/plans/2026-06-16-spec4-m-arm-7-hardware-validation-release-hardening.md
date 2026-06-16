# Plan — M-ARM-7: Hardware validation + release hardening (post-SPEC-4)

> **Status: draft follow-on after SPEC-4 feature completion.** This milestone adds **no new arm
> features**; it turns the shipped M-ARM-1..6 stack into a releaseable, bench-verified subsystem with
> live deploy/rollback proof, hardware-marked smoke coverage, and a recorded signoff artifact.
>
> **For Claude:** execute with `lore:execute`. **TDD mandatory** where code changes land (failing test
> first → implement → `scripts/check.sh` green). Hardware-marked tests stay opt-in and must skip
> cleanly without the bench environment. Shared decisions/discipline/invariants: see the
> [plan index](./2026-06-15-spec4-robot-arm-implementation.md). **Ask before any `git` commit.**

## Goal

Turn the software-complete arm stack into something that can be **trusted on real hardware**: prove the
current control/program/twin surfaces against a real Pi + arm stand, prove deploy/rollback with the arm
configured, and capture the release evidence in-repo so "green tests" and "bench-verified" are no
longer conflated.

## Realizes

- **Post-SPEC-4 operational closure:** operationalizes SPEC-4
  [`§4.2 Testing Strategy`](../specs/SPEC-4-pibot-robot-arm.md),
  [`§4.3 Rollout Strategy`](../specs/SPEC-4-pibot-robot-arm.md), and
  [`§4.4 Operational Readiness`](../specs/SPEC-4-pibot-robot-arm.md) for the arm stack.
- Closes the remaining **"bench-verify pending"** work still called out after M-ARM-2 and bridges the
  gap between automated gates green and an arm release/signoff claim.
- Reinforces **NFR-1**, **NFR-5**, and **NFR-8** on real hardware: safety preserved, optional-peripheral
  behavior proven on the bench, and release docs kept accurate.

## Depends on / blocks

- **Depends on:** M-ARM-2..6 shipped on `main`, a real Pi reachable via `PIBOT_TEST_HOST`, flashed arm
  boards, and a safe bench stand. Some sub-tasks also depend on whether the stand has the optional
  gripper/tool hardware installed and whether `pibot[arm-ik]` is installed on the Pi.
- **Blocks:** arm release/signoff; any claim that the full arm stack has been hardware-verified.

## Prerequisites (⬜ confirm with the user before 7.1)

- The bench Pi host/address (`PIBOT_TEST_HOST`) and, if needed, `PIBOT_TEST_USER` /
  `PIBOT_TEST_DEPLOY_BASE`.
- Whether the stand has the optional **gripper/tool** hardware fitted.
- Whether the stand has the optional **`pibot[arm-ik]`** extra installed.
- A clear, obstruction-free bench envelope so the short motion tests can run safely.

## Tasks

### 7.1 — Live arm integration suite

- **What:** add a new hardware-marked live suite for the arm surface. It should exercise the real
  agent/control path through `AgentClient` against the Pi: telemetry, e-stop/clear, enable/disable,
  homing, a short jog pulse, one conservative absolute move on a homed joint, and the persisted
  pose/program CRUD/run/stop surface. Keep every motion short, reversible, and explicitly gated behind
  env vars so CI and non-arm stands stay safe.
- **Files:** `tests/integration/test_arm_live.py` (new), any small shared live-test helpers if needed.
- **Test-first:** failing hardware-marked test that skips cleanly without the bench env, and once
  enabled fails if the real `/arm/telemetry` or `/arm/control`/pose/program surfaces regress.
- **Done when:** the suite passes on a real Pi + configured arm stand and remains opt-in / skipped
  cleanly without that hardware.

### 7.2 — Live deploy / rollback with the arm stack

- **What:** extend the real-Pi deploy smoke so it proves the **arm** survives deploy and rollback too:
  after `pibot deploy` and after rollback, `pibotd` serves `/arm/telemetry`, persisted pose/program
  routes still work, and Cartesian calls fail only with documented capability/runtime reasons
  (`"IK unavailable"`, not-homed, unreachable pose) rather than import/runtime crashes.
- **Files:** `tests/integration/test_deploy_live.py`, `deploy/requirements.txt`, and deploy/runtime
  helpers only if needed.
- **Test-first:** extend the existing live deploy test to fail when arm routes disappear or regress
  after deploy/rollback.
- **Done when:** deploy + rollback are proven on a real arm-equipped Pi and still skip cleanly without
  live hardware.

### 7.3 — Mission Control arm E2E flow

- **What:** add an Arm-screen E2E flow to the existing manual/host-marked Mission Control harness:
  connect → open Arm → home → jog → run a saved pose/program → confirm the twin tracks telemetry →
  e-stop/clear. This stays **manual / host-marked**, just like the existing Tauri E2E flows; do not
  pretend it belongs in CI.
- **Files:** `app/e2e/arm.e2e.ts` (new), `app/e2e/README.md`.
- **Test-first:** start from a failing/skeletal flow definition with real Arm-screen selectors and
  assertions, then flesh it out against the built `.app` harness.
- **Done when:** the arm flow is part of the documented host-marked E2E set and can be executed on the
  hardware stand before release.

### 7.4 — Arm hardware signoff artifact

- **What:** add a dedicated signoff/results page for the arm release journey, mirroring the existing
  repo signoff docs. It should record the preconditions, hardware-marked pytest commands, manual CLI
  journey, manual Mission Control journey, and the measured/signed-off results for home/jog/move/grip/
  tool/moveL/program/twin/e-stop/watchdog/deploy/rollback.
- **Files:** `docs/hardware-arm-signoff.md` (new), plus cross-links from `docs/runbooks/arm-operation.md`.
- **Test-first:** none beyond keeping repo docs internally consistent; this is a manual signoff artifact,
  not an automated suite. Add the cross-links in the same change so the signoff page is discoverable.
- **Done when:** the checklist exists in-repo, is linked from the runbook, and is ready to be filled for
  a release candidate.

### 7.5 — Release docs / status cleanup

- **What:** clean up the arm docs to distinguish **software shipped** from **hardware signed off**.
  Update the relevant plan status notes, operator docs, and release instructions so outstanding bench
  work is explicit and the bench env/commands are recorded once in a stable place.
- **Files:** `docs/runbooks/arm-operation.md`, `CLAUDE.md`, `docs/plans/2026-06-15-spec4-m-arm-2-gripper.md`,
  and this plan file.
- **Done when:** the arm release gate is explicit, operator-facing instructions are accurate, and the
  software-vs-hardware distinction is no longer ambiguous in repo docs.

## Milestone DoD

Hardware-marked arm live tests pass on a real Pi + configured arm and skip cleanly without hardware;
deploy/rollback is proven with the arm stack enabled; the Arm-screen E2E flow is part of the host-marked
release checklist; an arm hardware signoff page exists and is filled for the candidate build; and the
normal repo gate (`scripts/check.sh` + desktop gate) remains green.

## Notes / risks

- **Real motion hazard:** these tests move physical hardware. Require an explicit bench env (for example
  `PIBOT_TEST_HOST` plus an arm-specific opt-in like `PIBOT_TEST_ARM=1`) and keep motions conservative,
  short, and easy to abort.
- **No CI substitute:** the hardware-marked and Tauri-hosted E2E evidence is intentionally manual.
  Existing in-process tests stay necessary but are not sufficient for release signoff.
- **Capability variance across stands:** some benches will lack gripper/tool or `[arm-ik]`. Tests should
  detect capabilities and assert the documented degraded behavior rather than assuming every optional
  peripheral is installed.
- **Open-loop truth caveat:** after `disable`/back-drive/power loss, commanded position can drift from
  reality. Re-home before any absolute-move validation sequence.
