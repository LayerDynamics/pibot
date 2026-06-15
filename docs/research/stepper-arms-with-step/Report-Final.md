# Stepper robot arms that ship STEP (.step/.stp) — where to download them

**Goal:** find every open-source **stepper** robot arm that provides real **STEP** (neutral B-rep)
CAD — not STL meshes, not proprietary SLDPRT — and download it. **Headline:** open-source stepper
arms publishing loose STEP are **rare**. Beyond the 16 already cloned, four research agents (GitHub,
Hackaday/Instructables, model platforms, curated lists) found **3 new freely-downloadable** STEP
arms — all now downloaded — plus a small paid/login-gated tail and one unverifiable platform (GrabCAD).

## NEW — downloaded (the deliverable)

| Arm | Source | License | STEP | Local path |
|---|---|---|---|---|
| **BetaBots Robot Arm** (6-DOF, NEMA11/17/23/24) | [`4ndreas/BetaBots-Robot-Arm-Project`](https://github.com/4ndreas/BetaBots-Robot-Arm-Project) (386★) | GPL-3.0 | **9 `.stp`** — full `RobotV4.stp` assembly + 7 joints + gripper (`Green/step/`) | `resources/arms/betabots/` |
| **Teensy 6-DOF arm** (6-DOF, NEMA) | [`danieljhand/6_dof_robot_arm`](https://github.com/danieljhand/6_dof_robot_arm) + [Hackaday #205457](https://hackaday.io/project/205457) | GPL-3.0 | **6 `.step`** — one per joint (`3d step files/Joint 1-6/`) | `resources/arms/danieljhand-6dof/` |
| **3D-Printed Palletizer** (3-DOF, 3× NEMA17) | [Hackaday #182652](https://hackaday.io/project/182652), Files tab | none stated | **1 STEP** assembly ([direct CDN link](https://cdn.hackaday.io/files/1826527814583168/PalletizerRobot_V01.STEP), 7.4 MB) | `resources/arms/palletizer-hackaday/` |

BetaBots is the strongest find — clean per-part STEP, and historically **BCN3D Moveo descends from it**.
All GPL/none → **re-derive DH** (don't vendor the files), per PiBot's geometry-reuse policy.

## Known but NOT downloaded (with the honest reason)

- **Cults3D — 3 stepper+STEP arms, all PAYWALLED:** a 4-DOF SCARA ($8.75), "Robot ARM 6 axis"
  (Ruskomponen, STEP AP203+AP214, $5.81), "6 AXIS ROBOT ARM" (RiCkY/klabhesh, $6.58). Real STEP, but
  not free downloads — buy them if wanted.
- **GrabCAD — UNVERIFIED (login-gated):** every GrabCAD model/file page returned **HTTP 403** to the
  research agents. GrabCAD is the platform *most* likely to host free neutral STEP for stepper arms
  (candidates like "robotic-arm-with-nema-17-stepper-motors", "6-axis-stepper-robot"), so a
  **logged-in human opening the Files tab** is the single biggest remaining gap.
- **Printables / Thingiverse / MyMiniFactory:** every stepper arm checked was **STL-only** (mesh, no
  B-rep STEP). Zero in-scope hits.
- **Skipped as redundant/partial:** `Annin-Robot-Project` (AR2 predecessor — geometry already covered
  by the cloned AR2/AR3/AR4 lineage); `Mantis-Robot-Arm` (STEP only for the gripper accessory).
- **Excluded — servo, not stepper:** Manuel-1.0 (Dynamixel), reBot-DevArm, Pedro, charm, Jeffh1505,
  EvoArm, 3Ddynamics — several ship lots of STEP but are out of scope.

## Method / confidence
GitHub finds were verified by tree-enumeration; the 3 downloaded STEP sources were file-verified
(BetaBots/danieljhand by cloning + listing `.step`; Palletizer by `curl` + the `ISO-10303-21` header).
GrabCAD is the one acknowledged blind spot (403). Full per-agent detail + URLs in
`Agent{1..4}Findings.md` / `Agent{1..4}Sources.md` in this folder.
