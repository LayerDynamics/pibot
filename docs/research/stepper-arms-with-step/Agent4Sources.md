# Agent 4 Sources — Curated Lists + Lesser-Known Stepper Arms (STEP check)

All URLs below were actually fetched/searched during this research. "API-verified" means
the GitHub Trees API (`GET /repos/<owner>/<repo>/git/trees/<branch>?recursive=1`) was
queried and the listed file extensions came back in the response.

## Curated lists / aggregators mined

- **hobofan/collected-robotic-arms** — https://github.com/hobofan/collected-robotic-arms
  - Source of the BetaBots lead (listed there with CAD format "STEP, STL"). Also lists
    Thor, BCN3D Moveo, AR2 (already cloned) and commercial/servo arms (DOBOT, uArm, Niryo,
    7Bot, Bender, Lite Arm i2) that are out of scope.
- **adafruit/awesome-open-source-robotic-arms** — https://github.com/adafruit/awesome-open-source-robotic-arms
  - Yielded AR4 (cloned), Arctos (cloned), and servo/STL arms: reBot-DevArm (servo),
    Pedro 2.0 (servo+STL), Reachy 2, OpenExo, SCARA howtomechatronics. No new stepper STEP.
- **stephane-caron/awesome-open-source-robots** — https://github.com/stephane-caron/awesome-open-source-robots
  - Manipulators listed: Koch v1.1, low_cost_robot, Thor. Koch/low_cost are
    smart-servo learning arms (out of scope); Thor already cloned.
- **circuitdigest "Top 10 Open Source Robotic Arms 2025"** — https://circuitdigest.com/articles/top-10-opensource-robotic-arms-for-beginners
  - All 10 are servo hobby arms (SG90/MG995). Out of scope.

## NEW / candidate arms — primary-source verification

- **BetaBots Robot Arm (ChaozLabs)** — https://github.com/4ndreas/BetaBots-Robot-Arm-Project
  - README (raw): https://raw.githubusercontent.com/4ndreas/BetaBots-Robot-Arm-Project/master/README.md
    — points to Hackaday project 3800 + chaozlabs.de.
  - STEP files (API-verified, branch `master`): `Green/step/{RobotV4,Elbow,forearm,GripperMount,RotBase,Shoulder,Wrist,WristRot}.stp`
    and `ThreeFingerGripper/step/3_finger_gripper.stp`. License: GPL-3.0 (API).
  - Motor type (primary): https://hackaday.io/project/3800-3d-printable-robot-arm —
    "Joint one and two will be Nema24 … Joint 3 and 4 Regular Nema17 stepper and for the 5
    joint a HerkuleX DRS-0101"; "5 × … TB6560 Stepper Motor Driver Boards." → 6-axis,
    stepper-driven main arm. **NEW, in scope.**
  - NOTE: an earlier fetch of the WRONG Hackaday URL (`/project/12989-...`) returned Thor's
    motor data by mistake; the motor claim above is re-verified against the correct page 3800.

- **Chris-Annin/Annin-Robot-Project** — https://github.com/Chris-Annin/Annin-Robot-Project
  - API-verified (branch `master`): STEP shipped as `Step files/Step files.zip` (zip NOT
    opened). SolidWorks `.SLDPRT` source present; loose parts under `STL files/*.STL`.
    License GPL-3.0. Repo desc: "6 axis stepper motor robot."
  - This is the **predecessor of AR2** (already cloned) — geometry redundant.
  - "Step files" folder ref: https://github.com/Chris-Annin/Annin-Robot-Project/tree/master/Step%20files

- **4ndreas/Mantis-Robot-Arm** — https://github.com/4ndreas/Mantis-Robot-Arm
  - API-verified (branch `master`): only `.stp` is `MantisGripper/step/GripperM120_2.stp`.
    Arm body (`MantisRobotArm/`) is Inventor `.ipt`/`.iam` only — no `step/` folder.
    License NOASSERTION. → STEP = gripper accessory only, not the arm.

## EXCLUDED — checked, ruled out

- reBot-DevArm (servo) — https://github.com/Seeed-Projects/reBot-DevArm
- Pedro 2.0 (servo + STL) — https://github.com/almtzr/Pedro
- EvoArm (Dynamixel smart servo) — https://github.com/AliShug/EvoArm
- Alejo Restrepo robotic_arm (servo, per repo abstract) — https://github.com/alerest285/robotic_arm
  (project page: https://alerest285.github.io/projects/6DOF-Robot-Arm/)
- armour (stepper but 3-DOF Dobot, STL only) — https://github.com/paulmorrishill/armour
- RyanPaulMcKenna (NEMA17 but NO CAD geometry; firmware/electronics only) —
  https://github.com/RyanPaulMcKenna/Motor-driver-encoder-CAN-NEMA17
- cybot_arduino (stepper control code, no CAD) — https://github.com/quartit/cybot_arduino

## Already-cloned arms re-surfaced by the lists (coverage check, not new)

- Thor — https://github.com/AngelLM/Thor
- BCN3D Moveo — https://github.com/BCN3D/BCN3D-Moveo
- AR2 — https://github.com/Chris-Annin/AR2
- AR3, Faze4 — https://github.com/PCrnjak/Faze4-Robotic-arm
- RR1 — https://github.com/surynek/RR1
- SmallRobotArm — https://github.com/SkyentificGit/SmallRobotArm
- Martin-Ansteensen steppper-robot-arm — https://github.com/Martin-Ansteensen/steppper-robot-arm
- 6AR — https://github.com/fabien-prog/6AR-Open-Source-6-Axis-Robot
- Open6X — https://hackaday.io/project/181875-open6x-robot-arm
- Arctos — https://arctosrobotics.com/

## Searches run (queries)

- awesome open source robotic arms list github stepper STEP CAD
- best open source 6-axis robot arm 2025 stepper STEP file github DIY desktop
- github 6 axis robot arm "step files" nema17/nema23 stepper (-moveo -thor -faze4 -AR4)
- grabcad open source 6 axis robot arm stepper nema "step" download DIY -servo
- open source robot arm github stepper "step file" cycloidal/harmonic 6dof 2024/2025
- EvoArm open source robotic arm stepper/servo github CAD step
- Alejo Restrepo alerest285 6DOF stepper robot arm github repository CAD step files
- hackaday.io/github stepper robotic arm STEP "BetaBots"/"ChaozLabs"/cycloidal named project
