# Agent 2 Sources — off-GitHub STEP-hosting stepper robot arms

All HTTP checks below were run with `curl -sIL` (headers) against the live URLs on
2026-06-15. "200 / <bytes>" means a real, directly-fetchable file was confirmed.

## CONFIRMED STEP downloads (curl-verified)

- Palletizer STEP (Hackaday Files tab, direct):
  https://cdn.hackaday.io/files/1826527814583168/PalletizerRobot_V01.STEP
  → HTTP/2 200, content-length 7,739,374 (7.74 MB), application/octet-stream.
  Project: https://hackaday.io/project/182652-3d-printed-palletizing-robot-arm

- BetaBots full assembly STEP (GitHub raw, direct):
  https://raw.githubusercontent.com/4ndreas/BetaBots-Robot-Arm-Project/master/Green/step/RobotV4.stp
  → HTTP/2 200, content-length 32,415,368 (32.4 MB).
  STEP folder: https://github.com/4ndreas/BetaBots-Robot-Arm-Project/tree/master/Green/step
  Repo license (GitHub API /license): GPL-3.0.
  9 total .stp via trees API: Green/step/{Elbow,GripperMount,RobotV4,RotBase,Shoulder,Wrist,WristRot,forearm}.stp + ThreeFingerGripper/step/3_finger_gripper.stp
  Hackaday project page: https://hackaday.io/project/3800-3d-printable-robot-arm

- Teensy 6-DOF per-joint STEP (GitHub raw, direct; joint 1 spot-checked):
  https://raw.githubusercontent.com/danieljhand/6_dof_robot_arm/main/3d%20step%20files/Joint%201/robot_arm_joint_1.step
  → HTTP/2 200, content-length 8,064,010 (8.06 MB).
  6 .step files via trees API: "3d step files/Joint {1..6}/robot_arm_joint_{1..6}.step"
  Repo license (GitHub API /license): GPL-3.0. Repo: https://github.com/danieljhand/6_dof_robot_arm
  Hackaday project page: https://hackaday.io/project/205457-teensy-powered-6-dof-robot-arm
  Also on Hackaday Files tab: robot_arm_joint_3.step (9.76 MB), robot_arm_joint_6.step (2.38 MB).

## Checked but rejected (no fetchable STEP / not stepper / already known)

- CyBot cycloidal: https://hackaday.io/project/182821-3d-printed-cybot-cycloidal-6-axis-robot-arm
  (STL-only on Cults3D https://cults3d.com/en/3d-model/gadget/cybot-cycloidal-disk-robot-arm ;
  GitHub quartit/cybot_arduino + quartit/cybot_support = code/URDF only)
- Atlas 6DOF: https://hackaday.io/project/168259-atlas-6dof-3d-printed-universal-robot
  (STL-only; axes 2&3 are ODrive BLDC servos, not steppers)
- ARManda: https://hackaday.io/project/173330-3d-printable-robotic-arm-armanda
  (STL-only; GitHub mAzurkovic/robotic-arm has zero CAD files in tree)
- 28BYJ-48 arm: https://hackaday.io/project/186619-diy-robotic-arm-using-28byj-48-stepper-motors (STL-only)
- 3D Printed 6DOF: https://hackaday.io/project/168086-3d-printed-6dof-robotic-arm (no files released)
- PyBot SCARA: https://hackaday.io/project/175419-pybot-scara-robotic-arm-3d-printed-python
  (IGES not STEP: https://www.jjrobots.com/wp-content/uploads/2019/09/pybot-Robotic-Arm-3D-MODELS-IGES-V11.zip ;
  STL on Thingiverse https://www.thingiverse.com/thing:4579405)
- omartronics 6-DOF: https://omartronics.com/diy-6-dof-robotic-arm-a-step-by-step-guide-to-design-print-and-program/
  (SERVO arm — MG996R/SG90, out of scope)
- Skyentific 6DoF Printables: https://www.printables.com/model/5311-6dof-robot-arm-six-axis-3d-printed-robotic-arm
  (= SmallRobotArm, ALREADY KNOWN; GitHub SkyentificGit/SmallRobotArm)

## Instructables (login-gated — flagged, not directly fetchable)

WebFetch returns footer/nav only (JS-rendered); attachments require login. STEP presence
UNVERIFIED for all:
- https://www.instructables.com/DIY-Robot-Arm-6-Axis-with-Stepper-Motors/
- https://www.instructables.com/Build-a-Giant-3D-Printed-Robot-Arm/
- https://www.instructables.com/Yet-Another-3D-Printed-Robot-Arm/
- https://www.instructables.com/Robot-Arm-UStepper/

## Aggregator / lead pages used (for traceability)

- https://kingroon.com/blogs/3d-printing-guides/top-3d-printed-robot-arm-projects
  (NOTE: unreliable — falsely claimed CyBot ships STEP; treat its STEP/STL claims as untrusted)
- https://hackaday.com/tag/nema17/ , https://hackaday.com/tag/harmonic-drive/ (tag indexes)
- https://toolboxrobotics.com/robotic-arm-eb15 (TLS cert error on fetch — not assessed)

## Method notes

- GitHub file listings via: `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1`,
  grep for `.step"`/`.stp"`. License via `GET /repos/{owner}/{repo}/license` (spdx_id).
- Direct-fetchability proven by `curl -sIL` on raw.githubusercontent.com / cdn.hackaday.io.
- LLM page summaries were NOT trusted for the STEP-vs-STL determination — every CONFIRMED
  entry has a corresponding 200-status curl.
