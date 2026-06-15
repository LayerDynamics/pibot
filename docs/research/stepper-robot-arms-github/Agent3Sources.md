# Agent 3 Sources — Software / Control Stack & Kinematics/IK Reusability

Every URL below was fetched/queried during this research (via `gh api`, WebFetch, or WebSearch).
Repo file-trees and license fields were read directly from the GitHub API (primary source), not
inferred from blogs. Verification method noted per entry.

## AR4 (Annin Robotics) — HIGH reuse

- https://github.com/ycheng517/ar4_ros_driver — community ROS2 driver. **Verified via `gh api`:**
  license **MIT**, 149 stars, pushed 2026-04-04. Tree contains `annin_ar4_description` (URDF/xacro:
  `ar.urdf.xacro`, `ar_macro.xacro`, mk1/mk2/mk3 meshes), `annin_ar4_moveit_config` (full MoveIt2:
  `kinematics.yaml`, `ompl_planning.yaml`, `moveit_servo.yaml`, `pilz_planning.yaml`, SRDF),
  `annin_ar4_driver` (`teensy_driver.hpp`, `arduino_nano_driver.hpp`, `ar_hardware_interface.hpp`).
- https://raw.githubusercontent.com/ycheng517/ar4_ros_driver/main/annin_ar4_driver/src/teensy_driver.cpp
  — **WebFetch verified** the serial protocol: ASCII command strings, two-letter headers, single-
  letter joint identifiers (A,B,C…) + float values in **degrees**, `\n`-terminated. Examples:
  `STA2.1.0B…\n` (init), `MTA0123.45A1234.56\n` (move), `JP\n`→`JPA123.45B234.56…\n` (query).
- https://github.com/Annin-Robotics/ar4-hmi — **official** AR4 software library. `gh api`: language
  Python + C++ + CMake + Shell, **license NOASSERTION** (no clear OSS license), 32 stars, pushed
  2025-11-20. (Reason the community MIT driver is the safe reuse path.)
- https://github.com/ycheng517/ar4_ros_driver_examples — teleop/multi-arm examples (context only).
- https://github.com/ycheng517/ar4_hand_eye_calibration — hand-eye calib (context only).

## AR3 (Annin Robotics) — HIGH reuse

- https://github.com/ongdexter/ar3_core — **Verified via `gh api`:** license **MIT**, 120 stars.
  Tree contains `ar3_description/urdf/ar3.urdf` (**plain non-xacro URDF**) + `ar3.urdf.xacro` +
  meshes, and `ar3_moveit_config` (ROS1 MoveIt). This plain `.urdf` is the cleanest ikpy drop-in.
- https://github.com/RIF-Robotics/ar3_moveit2_config — **Verified via `gh api`:** ROS2/MoveIt2
  config, 3 stars, **no license field**, pushed 2023-09-04.
- https://github.com/kentavv/annin_robotics_ar3 — alt AR3 software (context).
- **Caveat:** AR3's *serial protocol* was **not** independently verified from source (only AR4's
  `teensy_driver.cpp` was fetched). The Findings note AR3's protocol as *inferred* Annin lineage,
  not a confirmed fact. It is non-blocking — kinematics reuse (the URDF) is protocol-independent.

## AR2 (Annin Robotics) — LOW (standalone; use AR3 geometry)

- `gh search repos "AR2 annin robot arm"` → **empty** (no Annin-owned AR2 repo on GitHub; the
  official AR2 ships only a Windows/Python GUI, ~2017 predecessor of AR3).
- https://github.com/wesleysliao/ros-AR2-arm-workspace — **Verified via `gh api`:** community catkin
  workspace, 2 stars; tree has `src/ROS_AR2_moveit_config` + `src/moveit_visual_tools` but **no
  `*_description`/URDF package surfaced** → no clean separable URDF for the seam.
- https://github.com/qsullivan11/ARCS_AGV — AR3/ARCS-derived (license null) confirms the
  AR2→AR3→ARCS lineage; AR2 geometry is subsumed by AR3's MIT `ar3.urdf`.

## BCN3D Moveo — HIGH (kinematics) / Medium (ROS1)

- https://github.com/jesseweisberg/moveo_ros — **Verified via `gh api`:** license **MIT**, 324
  stars, pushed 2023-12-30. Tree: `moveo_urdf/` (URDF + STL meshes), `moveo_moveit_config`
  (`kinematics.yaml`, SRDF, OMPL, catkin `.launch`), `moveo_moveit/msg/ArmJointState.msg` +
  `moveo_moveit_arduino/*.ino` (**rosserial joint-angle Arduino driver, NOT G-code**),
  `moveit_convert.cpp`.
- https://github.com/JJJau03/moveo_RoboticArm_ROS2 — community ROS2 fork (2 stars; context).
- https://github.com/logeshg2/Moveo_5-DOF_Software — alt Moveo software (context).

## Arctos — HIGH (kinematics) / Medium (whole arm)

- https://github.com/cr0Kz/ros2_arctos — **Verified via `gh api`:** license **Apache-2.0**, 16
  stars, pushed 2025-10-03. Packages live on feature branches; `feature/moveit_config_and_bringup`
  tree contains `arctos_description` (URDF + STL meshes + `kinematics.yaml`, `joint_limits.yaml`,
  `ros2_controllers.yaml`, SRDF). Default-branch HEAD has only meta files (confirmed branch layout:
  main/dev/feature/motor_driver/feature/moveit_config_and_bringup/feature/3-hardware-interface).
- https://github.com/Arctos-Robotics/ROS — **Verified via `gh api`:** license **MIT**, 93 stars.
  Tree (`arctos_moveit`, `arctos_urdf_description`, `ArmJointState.msg`, `moveit_convert.cpp`,
  `moveo_objrec_publisher.py`) shows it is a **Moveo-derived** stack (shared filenames). ROS1 MoveIt.
- https://github.com/Arctos-Robotics/arctosgui — ROS1 MoveIt GUI, 29 stars (context).
- https://github.com/Arctos-Robotics/Arctos-grbl-v0.1 — **GRBL/G-code** firmware (6-axis, Mega2560).
- https://github.com/Arctos-Robotics/GcodeCANBus — streams G-code to CAN bus (native protocol).
- https://github.com/Arctos-Robotics/CLMD-Closed-Loop-Motor-Driver — closed-loop CAN steppers.
- https://github.com/Arctos-Robotics/Matlab-Simulink-FK — forward-kinematics reference (context).

## Thor (AngelLM) — MEDIUM (copyleft-encumbered)

- https://github.com/AngelLM/Thor — **Verified via `gh api`:** mechanical/hardware repo, license
  **CC-BY-SA-4.0**, 1498 stars, pushed 2025-05-09. (DIY 3D-printable 6-DOF; no control software here.)
- https://github.com/AngelLM/Thor-ROS — **Verified via `gh api`:** **ROS2 Humble + MoveIt2**
  (`ws_thor/src/thor_moveit/config/kinematics.yaml` etc.) + Asgard React GUI + `thor_joystick`.
  License **CC-BY-SA-4.0**, 12 stars, pushed 2025-10-05.
- https://github.com/b-adkins/thor_arm_description — standalone ROS URDF pkg. **`gh api`:** license
  **GPL-3.0**, 7 stars (copyleft).
- http://thor.angel-lm.com/ + https://hackaday.io/project/12989-thor — **WebSearch confirmed:**
  firmware is a **GRBL modification (G-code)**; Asgard is React FK/IK web GUI; all source CC-BY-SA-4.0;
  6-DOF (yaw-roll-roll-yaw-roll-yaw), 750g payload, 625mm.

## EEZYbotARM — MEDIUM (servo, but best Python-IK reference)

- https://github.com/meisben/easyEEZYbotARM — **Verified via `gh api`:** license **MIT**, 103 stars,
  pushed 2023-10-23. Tree: `python_packages/easyEEZYbotARM/kinematic_model.py` (analytic FK/IK),
  `serial_communication.py`, `docs/kinematics/Forward_kinematics_EEZYbotARM_v2.pdf` +
  `Inverse_kinematics_EEZYbotARM.pdf`, `examples/example3_inverseKinematics.py`. **Note: RC-servo-
  driven, not stepper** — mismatch with framing, but the MIT analytic-IK Python module is the best
  reference for structuring PiBot's `IKSolver`.
- https://github.com/justbuchanan/eezybotarm-mk2-software — Arduino + Qt GUI (context).
- https://github.com/inaciose/ebamk2_description — small ROS URDF description (context).
- https://github.com/inaciose/eezybotarm — ROS package (context).

## Dummy-Robot (peng-zhihui) — LOW

- https://github.com/peng-zhihui/Dummy-Robot — **Verified via `gh api`:** **license null
  (all-rights-reserved)**, 15092 stars, pushed 2024-03-14, Chinese docs. Tree shows analytic IK
  **embedded in firmware**: `2.Firmware/Core-STM32F4-fw/Robot/algorithms/kinematic/6dof_kinematic.cpp`
  + `.h`. **No URDF**, kinematics welded to proprietary STM32 closed-loop board → not a reuse donor.

## WLkata Mirobot — LOW–MEDIUM (commercial closed firmware)

- https://github.com/matthewwachter/py-mirobot — **`gh api`:** MIT Python SDK (G-code), 19 stars.
- https://github.com/mushroom-x/wlkata-mirobot-python — Python SDK; examples confirm G-code control
  with `set_joint_angle`, `set_tool_pose`, interpolation (verified via `gh api` tree).
- https://github.com/kimsooyoung/mirobot_ros2 — **`gh api`:** **MIT**, ROS2; `mirobot_description`
  URDF + STL meshes present. (Community URDF is reusable; the robot itself is sealed commercial.)
- https://github.com/gabebear/WLkata-Mirobot-Firmware — Arduino/GRBL-derived firmware (context).

## PiBot integration target (internal — for grounding the verdicts)

- `/Users/ryanoboyle/pibot/pibot/arm/kinematics.py` — the `JointSolver` Protocol
  (`solve(target) -> dict[int, float]`, joint id → degrees), `DirectSolver`, `NamedPoseSolver`;
  docstring states an `IKSolver` drops into this interface once link geometry/DH/URDF is known.
- `/Users/ryanoboyle/pibot/pibot/ros2/` (`bridge.py`, `convert.py`) — PiBot's ROS2 bridge module.

## Search queries run (WebSearch / gh search)

- WebSearch: "Thor open source robot arm AngelLM Asgard control software GUI firmware GRBL ROS URDF"
- `gh search repos`: "moveo robot arm", "arctos robot arm", "thor robot arm ros", "AR3 robot arm",
  "AR4 robot arm annin", "annin robotics", "EEZYbotARM", "wlkata mirobot", "Thor 6 axis arm",
  "AR2 annin robot arm", "ar2 robot arm".
