# Agent 2 Findings — Off-GitHub / project-page STEP-hosting stepper robot arms

**Facet:** Hackaday.io, Instructables, and project/blog sites hosting open-source
**stepper** robot arms with downloadable **STEP** (.step/.stp) files — the Open6X pattern
(STEP lives on the project page / a Files tab / a Drive link, often cross-posted to GitHub
rather than living only in a curated GitHub topic).

**Verification standard:** A "STEP" claim is marked **CONFIRMED** only when I `curl -sI`'d
the actual file URL and got HTTP 200 + a real content-length, OR listed the file via the
GitHub trees API. LLM-summary claims of "STEP available" are treated as UNVERIFIED until
curled — this caught a kingroon blog that falsely claimed CyBot had STEP (it is STL-only).
Servo-only arms excluded. Already-known arms (Moveo, AR4, Faze4, Thor, Arctos, AR3,
PAROL6, SmallRobotArm, Open6X, AR2, Dummy-Robot, 6AR, Mirobot, RR1, mariohany01,
Martin-Ansteensen) are NOT re-reported as new — noted only for cross-ref.

## NEW in-scope hits — CONFIRMED stepper + directly-fetchable STEP (curl-verified)

| Project (URL) | STEP location + direct link | login-gated? | DOF | stepper | license | GitHub repo? | note |
|---|---|---|---|---|---|---|---|
| **3D Printed Palletizing Robot Arm** — https://hackaday.io/project/182652-3d-printed-palletizing-robot-arm | Hackaday **Files tab**. DIRECT: `https://cdn.hackaday.io/files/1826527814583168/PalletizerRobot_V01.STEP` | No | 3 (palletizer; 4th axis WIP) | 3× NEMA17 (e.g. 17HS15-1504S) | none stated | none found | **CONFIRMED**: curl → HTTP/2 200, content-length 7,739,374 (7.74 MB), application/octet-stream. Single full-assembly STEP, SolidWorks-authored. Palletizer geometry, not 6-DOF articulated. |
| **BetaBots "3D Printable Robot Arm" (Hackaday #3800)** — https://hackaday.io/project/3800-3d-printable-robot-arm | STEP on **GitHub** (Hackaday page → repo). Folder: `https://github.com/4ndreas/BetaBots-Robot-Arm-Project/tree/master/Green/step` . DIRECT full assembly: `https://raw.githubusercontent.com/4ndreas/BetaBots-Robot-Arm-Project/master/Green/step/RobotV4.stp` | No | 6 | NEMA23 (high-power driver, Arduino Due + RAMPS-FD) | **GPL-3.0** | yes — `4ndreas/BetaBots-Robot-Arm-Project` | **CONFIRMED**: 9× `.stp` files (Elbow, GripperMount, RobotV4 [full assy], RotBase, Shoulder, Wrist, WristRot, forearm, plus ThreeFingerGripper/step/3_finger_gripper.stp). RobotV4.stp curl → HTTP/2 200, content-length 32,415,368 (32.4 MB). Inventor-authored, neutral STEP exported. Classic Open6X pattern (Hackaday project, STEP on GitHub). |
| **Teensy-Powered 6-DOF Robot Arm (Hackaday #205457)** — https://hackaday.io/project/205457-teensy-powered-6-dof-robot-arm | STEP on **both** Hackaday Files tab AND GitHub. Files-tab samples: `robot_arm_joint_3.step` (9.76 MB), `robot_arm_joint_6.step` (2.38 MB). GitHub folder `3d step files/Joint N/`. DIRECT (joint 1): `https://raw.githubusercontent.com/danieljhand/6_dof_robot_arm/main/3d%20step%20files/Joint%201/robot_arm_joint_1.step` | No | 6 | steppers (NEMA size not stated on page); Teensy 4.1 controller | **GPL-3.0** | yes — `danieljhand/6_dof_robot_arm` | **CONFIRMED**: 6 per-joint `.step` files (Joint 1–6) in repo. Joint 1 curl → HTTP/2 200, content-length 8,064,010 (8.06 MB). "100% 3D-printable modular joints (all STEP files are included)." Per-joint STEPs, no single combined assembly file. |

## Rejected / out-of-scope (checked, NO fetchable STEP, or not a stepper arm)

| Project (URL) | Why rejected | Evidence |
|---|---|---|
| CyBot Cycloidal 6-Axis Arm — https://hackaday.io/project/182821-3d-printed-cybot-cycloidal-6-axis-robot-arm | STL-only (no STEP) | Primary page: "Stl files and description doc on Cults3D." 6-DOF, NEMA17, cycloidal. GitHub quartit/cybot_arduino (firmware) + quartit/cybot_support (URDF) — code only, no STEP. A kingroon blog falsely summarized "STEP: Yes" — contradicted by the source page. |
| Atlas 6DOF universal robot — https://hackaday.io/project/168259-atlas-6dof-3d-printed-universal-robot | STL-only AND not a pure stepper arm | Files tab = STL only, no STEP. Axes 2 & 3 are **BLDC servos (ODrive)**; only axis 1 NEMA23 + axes 4/5/6 NEMA17. Comments ask for files; full CAD not released. (Its OpenCyRe reducer is separately open-source.) |
| ARManda — https://hackaday.io/project/173330-3d-printable-robotic-arm-armanda | STL-only (no STEP) | Files tab = 7 `.STL` only; commenter asked for STEP → not provided. GitHub mAzurkovic/robotic-arm exists (branch master) but its full tree has **zero** CAD files (trees API). 4-DOF, 3× NEMA17 + 1× NEMA11. |
| DIY Robotic Arm using 28BYJ-48 — https://hackaday.io/project/186619-diy-robotic-arm-using-28byj-48-stepper-motors | STL-only | Page: "I have uploaded the STL file here." 28BYJ-48 steppers, 3-DOF + servo gripper. No STEP. |
| 3D Printed 6DOF Robotic Arm — https://hackaday.io/project/168086-3d-printed-6dof-robotic-arm | No files released | Creator: "I don't want to release the files yet." Files count = 0. NEMA8/11/17 mix, 6-DOF. |
| PyBot SCARA — https://hackaday.io/project/175419-pybot-scara-robotic-arm-3d-printed-python | **IGES**, not STEP | jjrobots hosts `pybot-Robotic-Arm-3D-MODELS-IGES-V11.zip` (IGES) + STL on Thingiverse:4579405. 3× NEMA17 + servo gripper, 5-DOF (3 arm + 2 clamp). No `.step`/`.stp`. |
| omartronics 6-DOF — https://omartronics.com/diy-6-dof-robotic-arm... | SERVO arm (out of scope) | Uses 3× MG996R + 3× SG90 servos, STL-only on Cults3D. Not a stepper arm. |
| Skyentific 6DoF (Printables #5311) | = SmallRobotArm (ALREADY KNOWN) | Printables → GitHub SkyentificGit/SmallRobotArm. Cross-ref only. |

## Instructables — platform note (per brief: flag login-gated)

Instructables candidates could not be content-verified: WebFetch returns only the page
footer/nav (JS-rendered), AND Instructables file attachments are **login-gated** (download
requires a free account). So even a real STEP attachment there is **NOT directly
fetchable** — flag login-gated. Candidates seen (motor = stepper; STEP attachment
unconfirmed):

| Project (URL) | DOF | stepper | STEP? | note |
|---|---|---|---|---|
| DIY Robot Arm 6 Axis (with Stepper Motors) — https://www.instructables.com/DIY-Robot-Arm-6-Axis-with-Stepper-Motors/ | 6 | yes | UNVERIFIED — login-gated | page body not machine-readable; attachments behind login |
| Build a Giant 3D Printed Robot Arm — https://www.instructables.com/Build-a-Giant-3D-Printed-Robot-Arm/ | 6-axis | yes | UNVERIFIED — login-gated | same |
| Yet Another 3D Printed Robot Arm — https://www.instructables.com/Yet-Another-3D-Printed-Robot-Arm/ | — | yes | UNVERIFIED — login-gated | same |
| UStepper Robot Arm — https://www.instructables.com/Robot-Arm-UStepper/ | — | yes (uStepper) | UNVERIFIED — login-gated | same |

## Summary

3 NEW arms with **CONFIRMED directly-fetchable STEP** (all curl-verified HTTP 200):
1. **Palletizer** (Hackaday Files tab, 1 assembly STEP, 7.7 MB, NEMA17, 3-DOF, no license).
2. **BetaBots #3800** (STEP on GitHub, 9 .stp incl. 32 MB full assembly, NEMA23, 6-DOF, GPL-3.0).
3. **Teensy 6-DOF #205457** (STEP on Hackaday Files + GitHub, 6 per-joint .step, NEMA steppers, 6-DOF, GPL-3.0).
