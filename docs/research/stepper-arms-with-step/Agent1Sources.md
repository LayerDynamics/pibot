# Agent 1 Sources — GitHub stepper arms with STEP

All repos verified via authenticated `gh` CLI (account `LayerDynamics`): tree listing
(`gh api repos/<r>/git/trees/HEAD?recursive=1`) grepped for `\.(step|stp)$`, plus
README / CAD-part-filename motor-type check. Release assets checked with `gh api
repos/<r>/releases` where in-tree STEP was absent.

## Verified NEW stepper arm WITH STEP (in scope)
- https://github.com/4ndreas/BetaBots-Robot-Arm-Project — 6-DOF, GPL-3.0, 386★.
  Confirmed STEP: `Green/step/{Elbow,Shoulder,Wrist,WristRot,RotBase,forearm,GripperMount,RobotV4}.stp`
  + `ThreeFingerGripper/step/3_finger_gripper.stp` (9 total); also a `Blue/step/` folder.
  Confirmed STEPPER: Inventor tree has `Nema11.ipt`, `Nema17.ipt`, `Nema17 Geared.ipt`,
  `Nema23.ipt`, `GearedStepper_RotBase*.ipt`, `StepperBase/`, `StepperMotorDriverMount.ipt`.

## STEP-having but SERVO → out of scope (flagged)
- https://github.com/mattweidman/Manuel-1.0 — 49 `.step` in `models/step/`; README:
  "All motors are from the Dynamixel X series" → servo. MIT, 162★.
- https://github.com/Jeffh1505/Robotic-Arm — 5 `.STEP` in `STEP Files/`; README: Pi Pico
  + SG90 servos + PCA9685 → servo. MIT.
- https://github.com/hrushikeshrv/charm — 9 `.stp` in `data/cad/step/`; CAD tree has
  `Servo Motor MG996R.ipt` + `Servo Motor Micro 9g.ipt` → servo. GPL-3.0.
- https://github.com/Seeed-Projects/reBot-DevArm — `.step` mounts/gripper under
  `hardware/reBot_B601_DM/3D_Printed_Parts/`; README: CAN servo motors
  (Damiao/Robostride/etc.) → servo. CERN-OHL-W-2.0 / Apache-2.0.
- https://github.com/almtzr/Pedro — 4x 360° mini servos → servo. Apache-2.0, 136★.

## Genuinely stepper but NO STEP published (don't re-chase)
- https://github.com/youssef14sawan/Aegis-V-A-High-Torque-Cycloidal-Robotic-Arm-with-CV-Guided-Autonomy
  — 5-axis stepper cycloidal; no loose STEP in tree, no release assets.
- https://github.com/thnsmmrs/cycloidal-robot-arm — ESP32 + DM542 stepper driver,
  cycloidal; no STEP in tree.
- https://github.com/xiaochutan123l/MyRobotArm-stepperMotor — closed-loop stepper; no STEP.
- https://github.com/NuwanJ/robot-arm-stepper — stepper; no STEP.

## Unverified (STEP may be zipped — needs download to confirm)
- https://github.com/gouldpa/Triple-Cycloidal-Robot-Arm-Proto-2 — only `Tri_proto_2.zip`
  / `Tri_proto_2_rev1.zip` in tree; likely NEMA17 cycloidal (per Hackaday project
  https://hackaday.io/project/166133-triple-cycloidal-robot-arm). Unzip to confirm STEP.

## Discovery infrastructure
- Curated lists mined by reading the **full README text** (not just URL-regex):
  - https://github.com/hobofan/collected-robotic-arms — lists BetaBots explicitly with
    "Open Hardware files formats: STEP,STL" (independent corroboration of my STEP find)
    and notes **BCN3D-Moveo is "originally based on the BetaBots-Robot-Arm-Project"**.
    Every other entry is commercial-closed (DOBOT/7Bot/uArm/Niryo) or open-but-STL-only/
    non-stepper (Lite Arm i2, ancastrog, jjshortcut servo, Idegraaf SCARA, Bender) —
    none add a NEW stepper+STEP arm. Thor (cloned) and BetaBots are the only STEP entries.
  - https://github.com/adafruit/awesome-open-source-robotic-arms — Hardware section:
    AR4-MK3 (cloned), Arctos (cloned), OpenExo (exoskeleton), Pedro (servo, flagged),
    Reachy 2 (humanoid SDK), HowToMechatronics SCARA (servo guide). No NEW stepper+STEP arm.
  - Net: list-mining added **zero** further in-scope arms beyond BetaBots (evidence-backed
    via full-text read, not a regex artifact).
- BetaBots was first found via cycloidal/3d-print repo search; the hobofan list then both
  confirmed its STEP format and showed it is the *ancestor* of the already-cloned Moveo
  (so it is genuinely new geometry, not a Moveo re-share).
- Hackaday cross-refs seen in web search: Open6X (cloned), Faze4 (cloned),
  Triple-Cycloidal (above).

## Method note
`gh search code --extension step ...` (with keyword) returned empty for nema17/6dof/
cycloidal/manipulator combos — STEP blobs are not reliably text-indexed by GitHub code
search, so absence there is NOT evidence the file is missing. Every confirmed STEP result
above came from direct tree enumeration, not code search.
