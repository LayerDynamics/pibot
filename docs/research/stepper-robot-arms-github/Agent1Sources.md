# Agent 1 Sources — Open-Source Stepper Robot Arms on GitHub

Every URL used during enumeration, with a short note on what it provided. "API" = queried
via `api.github.com/repos/...` on 2026-06-15 for authoritative stars / `pushed_at` /
license / archived status.

## GitHub REST API (authoritative metadata — primary)

- `https://api.github.com/repos/<owner>/<repo>` — pulled stars, last-commit date, license,
  archived flag, and redirect resolution for all repos below. Used for: AngelLM/Thor,
  AngelLM/Thor-ROS, BCN3D/BCN3D-Moveo, peng-zhihui/Dummy-Robot, Chris-Annin/AR2,
  Chris-Annin/AR3 (404 → confirms no first-party AR3 repo), Chris-Annin/AR4 (404),
  Annin-Robotics/ar4-hmi, Annin-Robotics/ar4_ros_driver, ycheng517/ar4_ros_driver,
  Arctos-Robotics/ROS (redirect resolved), Arctos-Robotics/arctosgui,
  PCrnjak/Faze4-Robotic-arm (→ Source-Robotics/Faze4-Robotic-arm), PCrnjak/PAROL6,
  SkyentificGit/SmallRobotArm, surynek/RR1, jk87/Open6X, Martin-Ansteensen/steppper-robot-arm,
  maxyuan6717/6_DOF_Robot_Arm, mariohany01/6-DOF-Robot, fabien-prog/6AR,
  RyanPaulMcKenna/Robotic-Arm (→ Motor-driver-encoder-CAN-NEMA17), meisben/easyEEZYbotARM,
  wlkata/mirobot-py, kentavv/annin_robotics_ar3, osiaeg/AR3_robotics.

## Repo pages fetched (WebFetch — README/about, secondary for DOF/motor facts)

- https://github.com/AngelLM/Thor — Thor: 6-DOF, steppers, GRBL/RRF, payload ~750 g, CC-BY-SA-4.0.
- https://github.com/BCN3D/BCN3D-Moveo — Moveo: Marlin firmware, educational 3D-printed arm.
- https://github.com/peng-zhihui/Dummy-Robot — closed-loop steppers + CAN, STM32 board, 6 joints.
- https://github.com/ycheng517/ar4_ros_driver — AR4 ROS2/MoveIt driver, Teensy controller.
- https://github.com/Annin-Robotics/ar4-hmi — official AR4-MK3 control SW, Teensy 4.1, 6-DOF stepper, non-commercial license.
- https://github.com/PCrnjak/Faze4-Robotic-arm — 6-axis cycloidal stepper arm, predecessor to PAROL6.
- https://github.com/PCrnjak/PAROL6-Desktop-robot-arm — 6-DOF stepper, Python API + ROS2, custom board.
- https://github.com/surynek/RR1 — RR1: NEMA23/17, Arduino Due, custom planetary gearboxes, encoders.
- https://github.com/SkyentificGit/SmallRobotArm — 6-DOF stepper, ~0.1 mm precision.
- https://github.com/Martin-Ansteensen/steppper-robot-arm — NEMA17 + RAMPS 1.4 vision pick-and-place arm.
- https://github.com/maxyuan6717/6_DOF_Robot_Arm — student 6-DOF arm, radio teleop.
- https://raw.githubusercontent.com/maxyuan6717/6_DOF_Robot_Arm/master/Big_Arm.ino — source inspection: `#include <Servo.h>`, 8× `Servo.attach()` → confirms **servo, not stepper** (reclassified/excluded).
- https://github.com/jk87/Open6X — confirmed repo exists, 6-axis, MIT, BOM/CAD/software dirs.
- https://github.com/Chris-Annin/AR2 — AR2: 6-axis stepper, Arduino Mega, ~1.4k stars.
- https://github.com/adafruit/awesome-open-source-robotic-arms — curated list (thin: AR4, Arctos, Reachy, Pedro).
- https://raw.githubusercontent.com/adafruit/awesome-open-source-robotic-arms/main/README.md — raw list contents.
- https://github.com/wlkata — WLKATA org repo list (mirobot-py, ROS pkgs, STL); no clear first-party firmware repo.

## WebSearch result pages / secondary sources

- https://github.com/AngelLM/Thor-ROS — ROS2 Humble + MoveIt2 stack + Asgard web UI for Thor.
- https://hackaday.com/2023/05/08/arctos-robotics-build-a-robot-arm-out-of-3d-printer-spares/ — Arctos overview, GRBL-mod, NEMA17/23.
- https://arctosrobotics.com/open-source-robotic-arm-2/ — Arctos: 6-axis, 600 mm reach, 2 kg, open/closed-loop (CAN) variants.
- https://github.com/Arctos-Robotics/arctosgui — Arctos v2 CAN + ROS1 MoveIt GUI.
- https://github.com/justbuchanan/eezybotarm-mk2-software — EEZYbotARM MK2 (servo) Qt GUI + Arduino.
- https://github.com/meisben/easyEEZYbotARM — EEZYbotARM Python/Arduino library; confirms **servo**-driven.
- https://www.hackster.io/news/chris-annin-calls-the-open-source-ar4-robot-arm-done-with-the-new-final-mark-5-revision-62b51e0ae555 — AR lineage AR2→AR3→AR4, Teensy/encoder evolution.
- https://hackaday.com/2019/10/17/open-source-arm-puts-robotics-within-reach/ — AR3 details, Arduino Mega → encoders.
- https://www.omc-stepperonline.com/ar2-open-source-robot-package-kit-... — AR2 stepper/driver/PSU kit (confirms NEMA steppers).
- https://github.com/kentavv/annin_robotics_ar3 — community AR3 software mirror (~10★, 2020).
- https://github.com/osiaeg/AR3_robotics — community AR3 software (0★, 2022).
- https://source-robotics.com/blogs/blog/faze4-robotic-arm-3d-printed-cycloidal-drives-in-robotics — Faze4 motor breakdown: 3× NEMA23, 2× NEMA17, 1× NEMA14, Teensy 3.5.
- https://hackaday.io/project/181875-open6x-robot-arm — Open6X: 6-axis, NEMA17/23, Arduino Mega, ~£400, 0.5 kg @ ~500 mm.
- https://github.com/PCrnjak/PAROL6-Desktop-robot-arm — PAROL6 stars/ROS/Python (also API-verified).
- https://github.com/fabien-prog/6AR-Open-Source-6-Axis-Robot — 6AR: Teensy 4.1 + RPi5, stepper/servo, JSON serial, beta.
- https://github.com/mariohany01/6-DOF-Robot — KUKA-style 6-DOF, full CAD→IK→ROS/MoveIt/Gazebo pipeline.
- https://github.com/RyanPaulMcKenna/Motor-driver-encoder-CAN-NEMA17 — from-scratch 6-DOF, NEMA17 + encoders + CAN.
- https://github.com/hobofan/collected-robotic-arms — discovery index of robotic-arm projects.
- https://www.wlkata.com/products/wlkata-best-6-axis-stem-educational-robot-arm-kit — Mirobot: 6-axis open-source desktop stepper arm (commercial).
- https://github.com/wlkata/mirobot-py — WLkata Mirobot Python SDK (MIT, ~12★).
