# Sources — Open-Source Stepper Robot Arms on GitHub (master list)

Deduped, grouped master list of every real URL used across the four research agents.
Star counts / `pushed_at` / license / archived status were pulled from the **GitHub REST
API** (`api.github.com/repos/...`) or `gh api` on **2026-06-15** (point-in-time, treat as
approximate). Repo file-trees and license fields were read directly from the API where
"verified" is noted. Everything else is a README/vendor/forum secondary source.

> **Note on malformed entries:** the task warned that `Agent4Sources.md` might contain
> `[object Object]` placeholders. On inspection that file was already clean (grouped URLs,
> no malformed entries) — nothing needed recovery or dropping.

## GitHub REST API (authoritative metadata — primary)

- [api.github.com/repos/&lt;owner&gt;/&lt;repo&gt;](https://api.github.com/repos) — stars, `pushed_at`,
  license, archived flag, and redirect resolution for every canonical repo below. Confirmed
  `Chris-Annin/AR3` and `Chris-Annin/AR4` return **404** (no first-party AR3/AR4 repo;
  site-distributed + community mirrors only).

## AR4 (Annin Robotics)

- [Annin-Robotics/ar4-hmi](https://github.com/Annin-Robotics/ar4-hmi) — official AR4-MK3 control SW; Python+C++; Teensy 4.1, 6-DOF stepper, encoder test files; **NOASSERTION** license.
- [ycheng517/ar4_ros_driver](https://github.com/ycheng517/ar4_ros_driver) — most-used community ROS2/MoveIt2 driver; **MIT**, ~150★, active 2026; `annin_ar4_description` (xacro URDF), `annin_ar4_moveit_config`, `annin_ar4_driver`.
- [ar4_ros_driver/README](https://github.com/Annin-Robotics/ar4_ros_driver/blob/main/README.md) — Teensy 4.1 + Arduino Nano, 6 joints, per-joint calibration, pyserial comms.
- [Annin-Robotics/ar4_ros_driver](https://github.com/Annin-Robotics/ar4_ros_driver) — Annin's own ros2_control driver (MIT).
- [teensy_driver.cpp (raw)](https://raw.githubusercontent.com/ycheng517/ar4_ros_driver/main/annin_ar4_driver/src/teensy_driver.cpp) — verified serial protocol: ASCII command strings, two-letter headers + single-letter joint tags + degree floats, `\n`-terminated (NOT G-code).
- [ycheng517/ar4_ros_driver_examples](https://github.com/ycheng517/ar4_ros_driver_examples) — teleop/multi-arm examples (context).
- [ycheng517/ar4_hand_eye_calibration](https://github.com/ycheng517/ar4_hand_eye_calibration) — hand-eye calibration (context).
- [robotsir/ar4_embodied_controller](https://github.com/robotsir/ar4_embodied_controller) — AR4/AR3 custom firmware using ikpy (community-activity signal).
- [robodk.com/robot/Annin-Robotics/AR4](https://robodk.com/robot/Annin-Robotics/AR4) — AR4 spec card (6-axis).
- [sprutcam.com/annin-ar4](https://sprutcam.com/annin-ar4/) — AR4 specs; payload ~1.9 kg, reach ~629 mm.
- [anninrobotics.com — learn-robotics-with-the-AR4](https://anninrobotics.com/learn-robotics-with-arduino-and-the-ar4-diy-robot-arm/) — AR4 DIY/Arduino+Python framing.
- [grokipedia.com — Annin Robotics AR4](https://grokipedia.com/page/Annin_Robotics_AR4) — AR4 overview (~$2–3k, machined-aluminum option).
- [stepperonline — AR4-MK3 electric package](https://www.omc-stepperonline.com/upgraded-ar4-robot-complete-electric-package-ar4-mk3-stepper-motor-driver-and-power-supply-ar4-mk3) — NEMA 17 + 23 w/ integrated encoders, ~$617.
- [anninrobotics.com — AR4 MK4 combo kit](https://anninrobotics.com/product-page/ar4-mk4-robot-combo-kit/) — ~$1,790 combined pricing context.
- [hackster.io — AR4 "done" / MK5 news](https://www.hackster.io/news/chris-annin-calls-the-open-source-ar4-robot-arm-done-with-the-new-final-mark-5-revision-62b51e0ae555) — AR2→AR3→AR4 lineage + maturity signal.

## AR3 (Annin Robotics)

- [ongdexter/ar3_core](https://github.com/ongdexter/ar3_core) — **MIT**, ~120★; ships a **plain non-xacro `ar3.urdf`** (cleanest ikpy drop-in) + `ar3_moveit_config` (ROS1).
- [RIF-Robotics/ar3_moveit2_config](https://github.com/RIF-Robotics/ar3_moveit2_config) — ROS2/MoveIt2 config, 3★, **no license field**.
- [kentavv/annin_robotics_ar3](https://github.com/kentavv/annin_robotics_ar3) — community AR3 software mirror, ~10★ (2020).
- [osiaeg/AR3_robotics](https://github.com/osiaeg/AR3_robotics) — community AR3 software (0★, 2022).
- [qsullivan11/ARCS_AGV](https://github.com/qsullivan11/ARCS_AGV) — AR3/ARCS-derived; confirms AR2→AR3→ARCS lineage.
- [robodk.com/robot/Annin-Robotics/AR3](https://robodk.com/robot/Annin-Robotics/AR3) — AR3 spec card (~1 kg, ~600 mm).
- [anninrobotics forum — AR3 payload](https://anninrobotics.com/forum/questions/what-is-the-payload-of-the-ar3-robot-arm/) — ~1.9 kg / 4 lb vs ~1 kg discrepancy.
- [hackaday — Open-source arm puts robotics within reach (AR3)](https://hackaday.com/2019/10/17/open-source-arm-puts-robotics-within-reach/) — AR2 Mega open-loop → AR3 adds encoders on Teensy 3.5; DM542T external drivers.

## AR2 (Annin Robotics)

- [Chris-Annin/AR2](https://github.com/Chris-Annin/AR2) — original 6-axis stepper arm, Arduino Mega, open-loop, ~1.45k★, stale (2019); custom ASCII serial.
- [wesleysliao/ros-AR2-arm-workspace](https://github.com/wesleysliao/ros-AR2-arm-workspace) — community catkin attempt, 2★; has a moveit_config dir but **no `*_description`/URDF** surfaced.
- [robodk.com/robot/Annin-Robotics/AR2](https://robodk.com/robot/Annin-Robotics/AR2) — AR2 spec card.
- [stepperonline — AR2 package kit](https://www.omc-stepperonline.com/ar2-open-source-robot-package-kit-23hs22-2804s-nema-23-stepper-motor) — AR2 stepper/driver/PSU kit (confirms NEMA steppers).

## BCN3D Moveo

- [BCN3D/BCN3D-Moveo](https://github.com/BCN3D/BCN3D-Moveo) — 5-DOF printable arm, **MIT**, ~1.9k★, dormant upstream; Marlin firmware (`FIRMWARE/Marlin_BCN3D_Moveo`), CAD + STL + EN/ES manuals.
- [jesseweisberg/moveo_ros](https://github.com/jesseweisberg/moveo_ros) — **MIT**, 324★; `moveo_urdf/` + `moveo_moveit_config` + `ArmJointState.msg` + **rosserial joint-angle Arduino driver** (NOT G-code) + `moveit_convert.cpp`. The kinematics donor + ArmManager twin.
- [jesseweisberg.com/moveo-with-ros](https://www.jesseweisberg.com/moveo-with-ros) — Mega 2560 + RAMPS 1.4, all joints stepper except servo gripper; ROS/URDF precedent (~$400).
- [Moveo Configuration_adv.h](https://github.com/BCN3D/BCN3D-Moveo/blob/master/FIRMWARE/Marlin_BCN3D_Moveo/Configuration_adv.h) — Marlin RAMPS pin model, dual-axis on 2nd extruder socket.
- [Moveo Marlin_main.cpp](https://github.com/BCN3D/BCN3D-Moveo/blob/master/FIRMWARE/Marlin_BCN3D_Moveo/Marlin_main.cpp) — confirms Marlin-based firmware.
- [JJJau03/moveo_RoboticArm_ROS2](https://github.com/JJJau03/moveo_RoboticArm_ROS2) — community ROS2 fork (2★, context).
- [logeshg2/Moveo_5-DOF_Software](https://github.com/logeshg2/Moveo_5-DOF_Software) — alt Moveo software (context).
- [bcn3d.com — Moveo overview](https://bcn3d.com/bcn3d-moveo-the-future-of-learning-robotic-arm/) — educational, fully printed.
- [all3dp.com — Moveo](https://all3dp.com/bcn3d-moveo-open-source-3d-printed-robot/) — 5-DOF, steppers + servo gripper, ~$400.
- [arduino forum — Moveo stepper payload](https://forum.arduino.cc/t/problem-with-stepper-motors/615193) and [Moveo issue #33](https://github.com/BCN3D/BCN3D-Moveo/issues/33) — real payload ~100 g on NEMA17 at safe current vs 2 kg target; NEMA17/14/23, 12–24 V; NEMA 23 (SM57HT112, 3 A) on heavy joint.
- [def-var.net — DIY Moveo BOM](https://def-var.net/project/diy-moveo-part-3-bill-of-materials-components/) — Moveo BOM walkthrough.

## Thor (AngelLM)

- [AngelLM/Thor](https://github.com/AngelLM/Thor) — iconic fully-printed 6-DOF, **CC-BY-SA-4.0**, ~1.5k★, latest tag v2.1 (Sep 2021); ~625 mm, ~750 g payload.
- [AngelLM/Thor-ROS](https://github.com/AngelLM/Thor-ROS) — ROS2 Humble + MoveIt2 (`thor_moveit`) + Asgard React GUI + `thor_joystick`; **CC-BY-SA-4.0**.
- [b-adkins/thor_arm_description](https://github.com/b-adkins/thor_arm_description) — standalone ROS URDF pkg, **GPL-3.0**, 7★ (copyleft).
- [AngelLM/Thor/wiki/FAQ](https://github.com/AngelLM/Thor/wiki/FAQ) — Arduino Mega + modified GRBL, actuators on a custom PCB.
- [AngelLM/ThorControlPCB](https://github.com/AngelLM/ThorControlPCB) — RAMPS-1.4-based shield, **up to 8 A4988 drivers**, 8 endstops, tool PWM (basis for the ~7-driver inference).
- [thor.angel-lm.com](http://thor.angel-lm.com/) — 6-DOF yaw-roll-roll-yaw-roll-yaw, ~625 mm, ~750 g, printed gears + GT2, <€350, 30+ builds in 17 countries.
- [hackaday.io — Thor project](https://hackaday.io/project/12989-thor) — community/maturity.
- [thingiverse — Thor STLs](https://www.thingiverse.com/thing:1743075) — fully printable STLs.

## Arctos

- [Arctos-Robotics/ROS](https://github.com/Arctos-Robotics/ROS) — **MIT**, ~93★; Moveo-derived ROS1 MoveIt stack (`arctos_moveit`, `arctos_urdf_description`, `ArmJointState.msg`, `moveit_convert.cpp`).
- [cr0Kz/ros2_arctos](https://github.com/cr0Kz/ros2_arctos) — **Apache-2.0**, 16★ (2025); ros2_control + MoveIt2; `arctos_description` URDF on `feature/moveit_config_and_bringup`.
- [Arctos-Robotics/arctosgui](https://github.com/Arctos-Robotics/arctosgui) — CAN-bus + ROS1 MoveIt control GUI (~29★).
- [Arctos-Robotics/Arctos-grbl-v0.1](https://github.com/Arctos-Robotics/Arctos-grbl-v0.1) — GRBL/G-code firmware (6-axis, Mega2560).
- [Arctos-Robotics/GcodeCANBus](https://github.com/Arctos-Robotics/GcodeCANBus) — streams G-code to CAN bus (native protocol).
- [Arctos-Robotics/CLMD-Closed-Loop-Motor-Driver](https://github.com/Arctos-Robotics/CLMD-Closed-Loop-Motor-Driver) — closed-loop CAN stepper driver.
- [Arctos-Robotics (org)](https://github.com/Arctos-Robotics) — org repo list incl. RoboDK + Matlab-Simulink-FK; CAD not in the open repos.
- [hackaday — Arctos from 3D-printer spares](https://hackaday.com/2023/05/08/arctos-robotics-build-a-robot-arm-out-of-3d-printer-spares/) — original Arctos: Mega2560 + CNC shield + A4988/DRV8825, mod GRBL, NEMA17/23, cycloidals, ~3 kg PLA, 600 mm, ~$326+, **CAD sold €39.95** (not open).
- [arctosrobotics.com/docs](https://arctosrobotics.com/docs/) — current build: closed-loop CANable v2 + MKS SERVO42D ×4 + SERVO57D ×2 over CAN; open-loop alt Mega + CNC shield + TMC2209 + GRBL.
- [arctosrobotics.com — open-source robotic arm](https://arctosrobotics.com/open-source-robotic-arm-2/) — 6-axis, 600 mm reach, 2 kg, open/closed-loop variants.
- [blog.arduino.cc — Arctos](https://blog.arduino.cc/2023/05/09/build-your-own-high-quality-arctos-robot-arm/) — overview (6-DOF, Arduino-based).
- [robotshop — Arctos kit](https://www.robotshop.com/products/arctos-robotics-arctos-6-dof-diy-robotic-arm-kit-self-assembly-600mm-reach-2kg-payload-arduino-esp32-ros-compatible) — 600 mm, 2 kg, Arduino/ESP32/ROS.

## Faze4 / PAROL6 (Source Robotics)

- [Source-Robotics/Faze4-Robotic-arm](https://github.com/Source-Robotics/Faze4-Robotic-arm) — fully printable 6-axis (redirect from PCrnjak/Faze4-Robotic-arm), **CERN-OHL-S-2.0**, ~860★; 3× NEMA23 + 2× NEMA17 + 1× NEMA14, printed cycloidals (J1–J5) + planetary (J6), Teensy 3.5, ~1000 parts.
- [PCrnjak/PAROL6-Desktop-robot-arm](https://github.com/PCrnjak/PAROL6-Desktop-robot-arm) — successor to Faze4; **GPL-3.0**, ~2.95k★, active 2026; custom STM32F446 + 6× TMC5160 board, Python API + ROS2.
- [source-robotics.com — Faze4 cycloidal drives](https://source-robotics.com/blogs/blog/faze4-robotic-arm-3d-printed-cycloidal-drives-in-robotics) — motor breakdown + ~$1k–1.5k cost class.
- [faze4 readthedocs](https://faze4-robotic-arm-docs.readthedocs.io/en/latest/About_faze4.html) — official build docs.
- [hackaday — Faze4 cycloidal gears](https://hackaday.com/2020/08/14/robotic-arm-sports-industrial-design-3d-printed-cycloidal-gears/) — low-backlash printed cycloidals feature.
- [printables — Faze4](https://www.printables.com/model/611889-faze4-robotic-arm) — community/maturity.
- [PAROL docs page3_1](https://source-robotics.github.io/PAROL-docs/page3_1/) and [tindie — PAROL6 control board](https://www.tindie.com/products/sourcerobotics/parol6-robot-control-board/) — STM32F446RE + 6× TMC5160, CAN, ESTOP, 64MB flash, ST-Link/SWD.

## Dummy-Robot (peng-zhihui)

- [peng-zhihui/Dummy-Robot](https://github.com/peng-zhihui/Dummy-Robot) — ~15.1k★, **no license**, semi-dormant (2024), Chinese docs; STM32F4 core + ESP32 + per-motor Ctrl-Step (STM32F1, FOC) over CAN; analytic IK welded into firmware (`6dof_kinematic.cpp`), **no URDF**.
- [hackaday — Dummy is not so dumb](https://hackaday.com/2022/02/21/dummy-the-robot-arm-is-not-so-dumb/) — closed-loop stepper controller per motor, harmonic drive, STM32 + ESP32.
- [unlir/XDrive](https://github.com/unlir/XDrive) — closed-loop STM32 driver referenced by Ctrl-Step (context).

## SmallRobotArm (Skyentific)

- [SkyentificGit/SmallRobotArm](https://github.com/SkyentificGit/SmallRobotArm) — compact 6-DOF stepper arm, **GPL-3.0**, ~1.46k★, stale (2019); ~0.1 mm precision.

## WLkata Mirobot

- [wlkata/mirobot-py](https://github.com/wlkata/mirobot-py) — official Python SDK, **MIT**, ~12★; G-code over serial; closed commercial firmware/board.
- [kimsooyoung/mirobot_ros2](https://github.com/kimsooyoung/mirobot_ros2) — **MIT** ROS2; `mirobot_description` URDF + meshes (community reuse).
- [matthewwachter/py-mirobot](https://github.com/matthewwachter/py-mirobot) — MIT Python SDK (G-code), 19★.
- [mushroom-x/wlkata-mirobot-python](https://github.com/mushroom-x/wlkata-mirobot-python) — Python SDK; `set_joint_angle`, `set_tool_pose`.
- [gabebear/WLkata-Mirobot-Firmware](https://github.com/gabebear/WLkata-Mirobot-Firmware) — Arduino/GRBL-derived firmware (context).
- [wlkata (org)](https://github.com/wlkata) — org repo list (SDK, ROS pkgs, STL); no clear first-party firmware repo.
- [wlkata.com — Mirobot kit](https://www.wlkata.com/products/wlkata-best-6-axis-stem-educational-robot-arm-kit) — 6-axis open-source desktop stepper arm (commercial).
- [ozrobotics — Mirobot](https://ozrobotics.com/shop/wlkata-mirobot-6-axis-mini-industrial-robot-for-education/) — "open source 6-axis," 0.2 mm repeatability; commercial assembled product.
- [Mirobot gitbook](https://lin-nice.github.io/mirobot_gitbook_en/13-wlkata.html) — spec/working-principle docs; ~150 g payload.

## EEZYbotARM (servo — flagged/excluded as the target, kept as Python-IK reference)

- [meisben/easyEEZYbotARM](https://github.com/meisben/easyEEZYbotARM) — **MIT**, ~100★; `kinematic_model.py` analytic FK/IK + `docs/kinematics/*.pdf` + `serial_communication.py`. **RC-servo-driven** — best Python IK *reference*, not a geometry donor.
- [justbuchanan/eezybotarm-mk2-software](https://github.com/justbuchanan/eezybotarm-mk2-software) — Qt GUI + Arduino (servo, context).
- [inaciose/ebamk2_description](https://github.com/inaciose/ebamk2_description) — small ROS URDF description (context).
- [inaciose/eezybotarm](https://github.com/inaciose/eezybotarm) — ROS package (context).
- [SphaeroX/EEZYbotARM-ESP32-Control](https://github.com/SphaeroX/EEZYbotARM-ESP32-Control) — ESP32 servo control (context).
- [instructables — EEZYbotARM Mk2](https://www.instructables.com/EEZYbotARM-Mk2-3D-Printed-Robot/) — 4-axis servo (MG946R + SG90), ABB IRB460 1:7 linkage.
- [cults3d — EEZYbotARM Mk3](https://cults3d.com/en/3d-model/tool/eezybotarm-mk3) / [thingiverse Mk3](https://www.thingiverse.com/thing:2838859) — Mk3 stepper variant, free STLs, small scale.
- [roboticsbd — EEZYbotARM Mk1](https://store.roboticsbd.com/robotics-parts/1163-eezybotarm-mk1-robot-arm.html) — Mk1: ~5 g payload, MG90S servos.

## Long-tail stepper repos (topic / keyword discovery)

- [surynek/RR1](https://github.com/surynek/RR1) — DIY 6-axis, **AGPL-3.0**, ~55★; NEMA23/17, Arduino Due, custom split-ring planetary gearboxes, encoders.
- [jk87/Open6X](https://github.com/jk87/Open6X) — low-cost 6-axis, **MIT**, ~15★; NEMA17/23 + MG996R gripper, Arduino Mega (open-loop), planetary gears, ~£400.
- [hackaday.io — Open6X](https://hackaday.io/project/181875-open6x-robot-arm) — 6-axis, NEMA17/23, Mega, ~£400, 0.5 kg @ ~500 mm.
- [fabien-prog/6AR](https://github.com/fabien-prog/6AR-Open-Source-6-Axis-Robot) — Teensy 4.1 + RPi5, stepper/servo joints, JSON serial, limit-switch homing; beta, not released.
- [Martin-Ansteensen/steppper-robot-arm](https://github.com/Martin-Ansteensen/steppper-robot-arm) — NEMA17 + 28BYJ-48 + 2 servos, Arduino Mega + RAMPS 1.4, vision pick-and-place.
- [mariohany01/6-DOF-Robot](https://github.com/mariohany01/6-DOF-Robot) — KUKA-style 6-DOF, full CAD→IK→MATLAB/Simulink→ROS+MoveIt+Gazebo pipeline.
- [RyanPaulMcKenna/Motor-driver-encoder-CAN-NEMA17](https://github.com/RyanPaulMcKenna/Motor-driver-encoder-CAN-NEMA17) — from-scratch 6-DOF, **MIT**; NEMA17 + encoders + CAN.
- [maxyuan6717/6_DOF_Robot_Arm](https://github.com/maxyuan6717/6_DOF_Robot_Arm) — **SERVO, excluded** (source `Big_Arm.ino` uses `#include <Servo.h>` + 8× `.attach()`); master-slave radio teleop.
- [Big_Arm.ino (raw)](https://raw.githubusercontent.com/maxyuan6717/6_DOF_Robot_Arm/master/Big_Arm.ino) — source inspection confirming servo classification.

## "3D-printer STM32 board → 6-DOF arm" feasibility (controller axis)

- [grblHAL/Controllers](https://github.com/grblHAL/Controllers) — grblHAL on STM32F103 sustains ~250 kHz/axis (3-axis) / ~150 kHz/axis (6-axis); supports up to 6 axes (key step-rate evidence).
- [sasan18s/grbl-stm32-6axis](https://github.com/sasan18s/grbl-stm32-6axis) — GRBL 1.1f ported to STM32F103/F407, 6-axis.
- [klipper.discourse — six-axis robots](https://klipper.discourse.group/t/six-axis-robots/668) and [6-axis compatible](https://klipper.discourse.group/t/6-axis-compatible/4099) — community XYZ→XYZABC 6-axis Klipper mods on printer MCUs.
- [AccelStepper MultiStepper](https://www.airspayce.com/mikem/arduino/AccelStepper/classMultiStepper.html) — constant-speed-only coordinated moves (no accel/decel); MULTISTEPPER_MAX = 10.
- [AccelStepper library](https://www.airspayce.com/mikem/arduino/AccelStepper/) — ~4 kSteps/s on 16 MHz AVR; ~30–100 kSteps/s on STM32-class MCUs.
- [gin66/FastAccelStepper](https://github.com/gin66/FastAccelStepper) — higher-rate timer/ISR-driven alternative (supports "drive steps from a HW timer").
- [dzid26/StepperServoCAN](https://github.com/dzid26/StepperServoCAN) — separate STM32F103C8 closed-loop CAN stepper (noted to avoid conflation with Arctos/Mirobot).

## Curated lists / roundups / scope-boundary context

- [adafruit/awesome-open-source-robotic-arms](https://github.com/adafruit/awesome-open-source-robotic-arms) — curated list (thin; surfaces AR4, Arctos, Reachy, Pedro).
- [hobofan/collected-robotic-arms](https://github.com/hobofan/collected-robotic-arms) — discovery index of robotic-arm projects.
- [circuitdigest — top 10 open-source robotic arms](https://circuitdigest.com/articles/top-10-opensource-robotic-arms-for-beginners) — servo-only list; used to confirm the stepper-vs-servo scope boundary.

## PiBot integration target (internal grounding)

- `/Users/ryanoboyle/pibot/pibot/arm/kinematics.py` — the `JointSolver` Protocol (`solve(target) -> dict[int, float]`, joint id → degrees), `DirectSolver`, `NamedPoseSolver`; an `IKSolver` drops into this interface once link geometry/DH/URDF is known.
- `/Users/ryanoboyle/pibot/pibot/ros2/` (`bridge.py`, `convert.py`) — PiBot's ROS2 bridge module.
