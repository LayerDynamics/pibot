# Plan Index — SPEC-4 PiBot Robot Arm implementation (M-ARM-1 … M-ARM-7)

> **For Claude:** this is the **umbrella index**. Each milestone has its own standalone plan (linked
> below) — execute one at a time with `lore:execute`. The shared **decisions**, **discipline**, and
> **invariants** here apply to every milestone plan. M-ARM-1..6 realize
> [SPEC-4](../specs/SPEC-4-pibot-robot-arm.md); **M-ARM-7 is a post-SPEC-4 follow-on** that closes the
> live-hardware validation and release-hardening work the spec leaves manual. Together they close the
> gaps in [`OtherArms.md`](../research/stepper-robot-arms-github/OtherArms.md) §6A/§6B and then carry
> the arm to release readiness.

## Goal

Take PiBot's arm from "built + safety-correct + read-only telemetry" to a controllable, programmable,
kinematics-aware manipulator — **without rebuilding the layered firmware safety or the sizing
calculator** (preserve them as constraints). Wire the existing motion engine end-to-end, then add
gripper, an in-tree kinematic model, FK/IK behind the `JointSolver` seam, trajectories +
teach/playback persistence, a live 3-D twin, and finally the real-hardware validation / release
evidence needed to trust the full stack on the bench.

## Milestone plans

| Milestone | Plan file | Realizes | Closes |
|---|---|---|---|
| **M-ARM-1** Motion control surface | [`…-m-arm-1-control-surface.md`](./2026-06-15-spec4-m-arm-1-control-surface.md) | FR-1..6 | §6B-1, §6A motion-UI |
| **M-ARM-2** Gripper / end-effector | [`…-m-arm-2-gripper.md`](./2026-06-15-spec4-m-arm-2-gripper.md) | FR-7,8 | §6B-2 |
| **M-ARM-3** Kinematic model + FK | [`…-m-arm-3-kinematic-model-fk.md`](./2026-06-15-spec4-m-arm-3-kinematic-model-fk.md) | FR-9,10,11 | §6B-4 (+ FK of §6A) |
| **M-ARM-4** Inverse kinematics | [`…-m-arm-4-ik.md`](./2026-06-15-spec4-m-arm-4-ik.md) | FR-12,13,14 | §6A (A.5) |
| **M-ARM-5** Trajectories + teach/playback | [`…-m-arm-5-trajectories-teach-playback.md`](./2026-06-15-spec4-m-arm-5-trajectories-teach-playback.md) | FR-15,16,17 | §6A (A.4) + §6B-3 |
| **M-ARM-6** 3-D twin | [`…-m-arm-6-3d-twin.md`](./2026-06-15-spec4-m-arm-6-3d-twin.md) | FR-18 | §6B-5 |
| **M-ARM-7** Hardware validation + release hardening | [`…-m-arm-7-hardware-validation-release-hardening.md`](./2026-06-16-spec4-m-arm-7-hardware-validation-release-hardening.md) | post-SPEC-4 ops closure (NFR-1,5,8) | hardware-marked signoff + release readiness |

> **Note:** M-ARM-7 is intentionally **outside** the original SPEC-4 FR-1..18 feature map. It is the
> release-confidence milestone: deploy/rollback on a real Pi + arm, hardware-marked smoke coverage,
> Mission Control arm E2E, and a signoff artifact that records the bench results.

## Decisions locked (from `/lore:plan` discovery, 2026-06-15)

1. **Scope:** all six milestones, full task detail (one plan file each).
2. **IK:** **numeric `ikpy`** behind an optional `pibot[arm-ik]` extra, **lazy-imported**, so
   `pibot.arm` core, the CLI, and `agent` stay stdlib-light (mirrors the `[ml]` boundary). Analytic
   solvers remain a future drop-in behind the same seam. (Resolves SPEC OQ-1.)
3. **Seed geometry:** **vendor an MIT donor URDF** — **AR3** (`resources/arms/ar3/ar3_core/
   ar3_description/urdf/ar3.urdf.xacro`, 6-DOF) for a 6-DOF arm, or **Moveo** (`resources/arms/moveo/
   moveo_ros/moveo_urdf/urdf/moveo_urdf.urdf`, 5-DOF) for 5-DOF — adapt link lengths to PiBot's arm,
   load with `ikpy.Chain.from_urdf_file`. Carry the donor's MIT attribution. (Resolves SPEC OQ-2.)
4. **Test cadence:** **test-first (TDD)** per task.
5. **Gripper:** servo (PWM) on the spare **E0** channel (SPEC D4); 6 DOF, **3+3** board split (SPEC OQ-4).

## Discipline (applies to every milestone plan)

- **TDD:** (a) write/extend the named test so it fails for the right reason; (b) run it, confirm the
  failure; (c) implement; (d) `bash scripts/check.sh` green = task done. Never claim done without
  running the gate.
- **Definition of done (per task):** `scripts/check.sh` green — ruff + ruff-format + mypy --strict +
  pytest ≥ 80 % coverage (zero skips) **and** the desktop gate (vitest + tsc + eslint + cargo) when the
  task touches `app/`. Firmware tasks additionally: STM32 compile + echo-stand round-trip.
- **Safety invariant (NFR-1):** every new motion path goes through the host gate **and** the unchanged
  firmware safety; e-stop must stay reachable even if IK/trajectory code faults. Add a regression test
  for the safety behavior in every milestone that adds a motion path.
- **`[ml]`/stdlib-light invariant (NFR-2):** no numpy/ikpy import at module load in `pibot.arm` core,
  CLI, or `agent`. An import-guard test enforces this (M-ARM-4 task 4.3).
- **Optional-peripheral invariant (NFR-5):** absent arm hardware must never break `pibotd`/MC startup;
  arm routes return a clean "no arm configured".
- **Docs accuracy (NFR-8):** when a task moves a gap from "missing" → "shipped", update `OtherArms.md`,
  the relevant milestone plan, and `CLAUDE.md`'s agent-endpoint/firmware-verb lists in the **same**
  change.
- **Ask before any `git` commit.** Confirm the hardware blanks (⬜) with the user before the task that
  needs them.

## Baseline already shipped (do NOT rebuild)

Firmware joint control + safety + homing (`firmware/pibot_arm_stm32`); `ArmManager` routing +
`move_synchronized` (`pibot/arm/manager.py`); `JointSolver`/`DirectSolver`/`NamedPoseSolver` seam
(`pibot/arm/kinematics.py`); sizing calculator (`pibot/arm/sizing.py`); read-only telemetry path
(`agent` `GET /arm/telemetry`, MC `GET /api/arm/telemetry`, `Arm.tsx` bars); config
(`pibot/config.py:55–61`). Existing tests: `test_arm_manager.py`, `test_arm_kinematics.py`,
`test_arm_protocol.py`, `test_arm_sizing.py`, `test_agent_arm.py`, `test_mc_arm.py`, `armStore.test.ts`.

## Dependency order

```text
M-ARM-1 ──┬─> M-ARM-2  (gripper rides the control surface)
          └─> M-ARM-5  (programs drive motion through the surface)
M-ARM-3 ──┬─> M-ARM-4 ─> M-ARM-5 (Cartesian paths)
          └─> M-ARM-6  (twin needs the URDF)
```

M-ARM-1 and M-ARM-3 are the two roots and can proceed in parallel. M-ARM-3 unblocks IK, Cartesian
trajectories, and the twin together.

## Hardware blanks to confirm (⬜)

1. Gripper servo channel/pins + min/max angle + optional pneumatic digital-out pin (M-ARM-2).
2. Donor URDF choice (AR3 6-DOF vs Moveo 5-DOF) + the real PiBot arm link lengths / joint limits to
   adapt (M-ARM-3).
3. Final joint count (5 vs 6) and board split — baseline 6 DOF / 3+3 (SPEC OQ-4).

## Sources

- [SPEC-4](../specs/SPEC-4-pibot-robot-arm.md) (requirements → milestones → traceability).
- [`OtherArms.md`](../research/stepper-robot-arms-github/OtherArms.md) (the gaps each milestone closes).
- [`2026-06-13-pibot-arm-control.md`](./2026-06-13-pibot-arm-control.md) (A.1–A.3 shipped baseline).
- Verified code (this session): `firmware/pibot_arm_stm32/pibot_arm_stm32.ino`,
  `pibot/arm/{manager,kinematics,sizing}.py`, `agent/app.py`, `pibot/mc/routes_arm.py`,
  `pibot/control/client.py`, `pibot/mc/robot_link.py`, `app/src/screens/Arm.tsx`, `pibot/config.py`,
  `pyproject.toml`.
