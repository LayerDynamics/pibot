# Plan — M-ARM-3: Kinematic model + Forward kinematics (SPEC-4)

> **For Claude:** execute with `lore:execute`. **TDD mandatory** (failing test first → implement →
> `scripts/check.sh` green). Shared decisions/discipline/invariants: see the
> [plan index](./2026-06-15-spec4-robot-arm-implementation.md). **Ask before any `git` commit.**

## Goal

Land a kinematic model in the tree and compute forward kinematics (joint angles → end-effector pose).
This is the single highest-fan-out milestone: it unblocks IK (M-ARM-4), Cartesian trajectories
(M-ARM-5), and the 3-D twin (M-ARM-6). Per the locked decision, the model **vendors an MIT donor URDF**
(AR3 6-DOF / Moveo 5-DOF) adapted to PiBot's link lengths.

## Realizes

- SPEC-4 **FR-9, FR-10, FR-11**; closes `OtherArms.md` **§6B-4** (no in-tree kinematic model) and the
  **FK** part of §6A.

## Depends on / blocks

- **Depends on:** the shipped baseline only (independent root — can run in parallel with M-ARM-1).
- **Blocks:** M-ARM-4 (IK loads this model), M-ARM-5 (Cartesian paths), M-ARM-6 (twin renders this URDF).

## Prerequisites (⬜ confirm with the user before 3.1)

- **Donor choice:** AR3 (`resources/arms/ar3/ar3_core/ar3_description/urdf/ar3.urdf.xacro`, 6-DOF) vs
  Moveo (`resources/arms/moveo/moveo_ros/moveo_urdf/urdf/moveo_urdf.urdf`, 5-DOF).
- **Real PiBot arm link lengths / joint limits** to adapt into the URDF (from the built arm / sizing
  config).

## Tasks

### 3.1 — Geometry package

- **What:** new `pibot/arm/geometry/` — vendor the chosen **MIT** donor URDF (expand the AR3 xacro once
  to a plain URDF, or copy Moveo's plain URDF), adapt link lengths/limits to PiBot's arm, include the
  required meshes (or primitive collisions), and add a `LICENSE`/attribution note crediting the MIT
  donor. Provide a `load()` helper returning the URDF path + parsed joint metadata.
- **Files:** `pibot/arm/geometry/__init__.py`, `pibot/arm/geometry/pibot_arm.urdf`,
  `pibot/arm/geometry/README.md` (source + MIT attribution), meshes as needed.
- **Test-first:** `tests/test_arm_geometry.py` — URDF loads, expected joint count, joint limits mirror
  `arm_joint_limits` config.
- **Done when:** the model loads and matches config; gate green.

### 3.2 — Forward kinematics

- **What:** add `ForwardKinematics` to `pibot/arm/kinematics.py` — joint angles → EE pose `(x,y,z,
  rx,ry,rz)` via the geometry model, using an ikpy chain's `forward_kinematics` (**lazy-imported**; the
  module-level import of `pibot.arm.kinematics` must stay numpy-free). Handle the deg↔rad and
  joint-order shim between PiBot logical joints and the URDF chain.
- **Files:** `pibot/arm/kinematics.py`.
- **Test-first:** extend `tests/test_arm_kinematics.py` — a known joint set → expected pose within
  tolerance (runs with `arm-ik` installed; see M-ARM-4 task 4.1 for the CI install).
- **Done when:** FK matches expected poses; `import pibot.arm.kinematics` still imports without numpy.

### 3.3 — Sizing emits geometry

- **What:** add a `from_sizing()` / `--emit-urdf` path to `pibot/arm/sizing.py` that turns the sizing
  link lengths + joint limits into the geometry URDF, so the model, the firmware `JCFG`, and the sizing
  calculator share one source of truth (FR-10). **Do not change** the sizing math (SPEC N6).
- **Files:** `pibot/arm/sizing.py`.
- **Test-first:** extend `tests/test_arm_sizing.py` — emitted URDF link lengths/limits equal the input
  config.
- **Done when:** sizing emits a model consistent with config; gate green.

### 3.4 — FK in the stack

- **What:** augment `/arm/telemetry` with a `pose` field (present only when the geometry model +
  `arm-ik` are available; absent → no crash), surface it in `pibot arm telemetry`, and add an EE-pose
  readout to the Arm screen.
- **Files:** `agent/app.py`, `pibot/cli.py`, `app/src/screens/Arm.tsx`, `app/src/stores/armStore.ts`.
- **Test-first:** extend `tests/test_agent_arm.py` (pose present when model loaded; cleanly absent
  otherwise) + `armStore.test.ts`.
- **Done when:** live EE pose shows in telemetry/CLI/UI when a model is configured; gates green.

### 3.5 — Docs

- **What:** `pibot/arm/geometry/README.md` records the donor source + MIT license; mark `OtherArms.md`
  §6B-4 shipped; note the geometry package in `CLAUDE.md`'s arm section.
- **Files:** `pibot/arm/geometry/README.md`, `docs/research/stepper-robot-arms-github/OtherArms.md`,
  `CLAUDE.md`.
- **Done when:** docs accurate, license attribution present (NFR-8).

## Milestone DoD

In-tree URDF/DH loads; live EE pose in telemetry/CLI/UI; sizing emits a matching model; core still
imports without numpy; `scripts/check.sh` + desktop gate green.

## Notes / risks

- **Geometry/`JCFG` drift (SPEC R3):** the sizing emitter (3.3) is the guard — derive dimensions from
  one source; add an FK sanity check vs a measured pose during hardware bring-up.
- Vendoring a donor URDF is license-safe **only** for the MIT donors (AR3/Moveo); keep the attribution
  note (donor licensing rule, `OtherArms §9`).
