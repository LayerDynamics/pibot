# PiBot arm kinematic model (`pibot/arm/geometry/`)

The in-tree kinematic model for the 6-DOF PiBot arm — `pibot_arm.urdf` plus the `load()` /
`generate_urdf()` helpers in [`__init__.py`](./__init__.py). Forward kinematics (M-ARM-3 task 3.2)
loads this URDF into an [`ikpy`](https://github.com/Phylliade/ikpy) chain; the 3-D twin (M-ARM-6)
renders it.

## How it's built — generated, not vendored

The URDF is **generated, not copied from a donor repo**. Two paths produce one:

- The **committed `pibot_arm.urdf`** is `generate_urdf(default_joints())` — a generic, self-consistent
  6-DOF placeholder (`base_link` → 6 revolute joints, each a primitive cylinder along +Z → a fixed
  `tool0` tip) whose joint **names match their axes** (base/shoulder/elbow + roll-pitch-roll wrist).
- `pibot/arm/sizing.py`'s `emit_urdf` produces a URDF from any real `ArmSpec`, so the **firmware
  `JCFG`, the sizing calculator, and the model share one source of truth** (SPEC R3, anti-drift) once
  you regenerate from *your* measured arm config:

  ```bash
  # generate the model from a real arm config (the example below is illustrative)
  python -m pibot.arm.sizing examples/arm-generic-6dof.toml --emit-urdf > pibot/arm/geometry/pibot_arm.urdf
  ```

The committed model uses **`⬜ TUNE` placeholder** lengths/limits until the built arm is measured —
its poses are self-consistent but not yet the real arm. `emit_urdf` assigns joint axes by index
(the AR3 6R convention), so order your config base→tip with that wrist convention when you regenerate.

## Attribution

The **6-revolute joint-axis convention** (base yaw → shoulder/elbow pitch → wrist roll/pitch → tool
roll) follows the **AR3** robot arm:

> AR3 — Copyright (c) 2021 Dexter Ong — **MIT License**
> <https://github.com/ongdexter/ar3_core> (vendored at `resources/arms/ar3/`)

No AR3 source files, meshes, or URDFs are copied into this package — only the joint-axis convention is
reused — but the AR3 MIT license and copyright are credited here per the donor-licensing rule
(`docs/research/stepper-robot-arms-github/OtherArms.md` §9). AR3's full MIT license text is at
`resources/arms/ar3/ar3_core/LICENSE`.

## No numpy at import

This package is pure stdlib (`xml.etree`) and **must import without numpy** so the `pibot.arm` core,
CLI, and agent stay stdlib-light (NFR-2). numpy/ikpy enter only through forward/inverse kinematics
behind the optional `pibot[arm-ik]` extra.
