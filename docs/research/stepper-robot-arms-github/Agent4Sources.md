# Agent 4 Sources — Viability Research

Every URL fetched/searched for the viability facet, with a short note on what it provided.
Figures from these sources are **approximate** (costs, stars, payloads drift over time).

## Annin AR4 / AR3 / AR2

- https://robodk.com/robot/Annin-Robotics/AR4 — AR4 RoboDK spec card (6-axis).
- https://sprutcam.com/annin-ar4/ — AR4 specs/applications; payload ~1.9 kg, reach ~629 mm.
- https://anninrobotics.com/learn-robotics-with-arduino-and-the-ar4-diy-robot-arm/ — AR4 DIY/Arduino+Python framing.
- https://grokipedia.com/page/Annin_Robotics_AR4 — AR4 overview (open-source, ~$2–3k build, 6-axis, machined-aluminum option).
- https://robodk.com/robot/Annin-Robotics/AR3 and .../AR2 — AR3/AR2 spec cards (6-axis, ~1 kg, ~600 mm).
- https://anninrobotics.com/forum/questions/what-is-the-payload-of-the-ar3-robot-arm/ — AR3 payload thread (cited ~1.9 kg / 4 lb vs ~1 kg in spec cards).
- https://www.hackster.io/news/chris-annin-calls-the-open-source-ar4-robot-arm-done-with-the-new-final-mark-5-revision-62b51e0ae555 — AR4 MK5 "final revision" news; project maturity signal.
- https://www.omc-stepperonline.com/upgraded-ar4-robot-complete-electric-package-ar4-mk3-stepper-motor-driver-and-power-supply-ar4-mk3 — AR4-MK3/4 electric pkg (NEMA 17 + NEMA 23 w/ integrated encoders), ~$617.
- https://anninrobotics.com/product-page/ar4-mk4-robot-combo-kit/ — AR4 MK4 combo kit pricing context (~$1,790 combined).
- (search) AR4 uses **Teensy 4.1** controller; 6 drivers; moved to motors with integrated encoders.

## AR4 software/maturity (for activity + license signals)

- https://github.com/ycheng517/ar4_ros_driver — **~149★, MIT, active (ROS2 Jazzy, Release 3.0.0 Dec 2024)**; supports AR4 MK1/MK2/MK3 + servo gripper; MoveIt2 + Gazebo.
- https://github.com/robotsir/ar4_embodied_controller — AR4/AR3 custom firmware (ikpy kinematics) — community-activity signal.

## BCN3D Moveo

- https://github.com/BCN3D/BCN3D-Moveo — **~1.9k★, MIT**, few commits (dormant upstream); fully 3D-printed; Arduino/Marlin firmware; CAD + STL + manuals (EN/ES).
- https://github.com/BCN3D/BCN3D-Moveo/blob/master/FIRMWARE/Marlin_BCN3D_Moveo/Marlin_main.cpp — confirms Marlin-based firmware.
- https://bcn3d.com/bcn3d-moveo-the-future-of-learning-robotic-arm/ — Moveo overview (educational, fully printed).
- https://all3dp.com/bcn3d-moveo-open-source-3d-printed-robot/ — 5-DOF, steppers + servo gripper, ~$400 build.
- https://www.jesseweisberg.com/moveo-with-ros and https://github.com/jesseweisberg/moveo_ros — **ROS/MoveIt + URDF** (URDF from SolidWorks); RAMPS 1.4 + Arduino Mega 2560; ~$400.
- https://forum.arduino.cc/t/problem-with-stepper-motors/615193 and https://github.com/BCN3D/BCN3D-Moveo/issues/33 — real-world payload caveat (~100 g on NEMA17 at safe current vs 2 kg target); NEMA 17/14/23, 12–24 V.
- https://def-var.net/project/diy-moveo-part-3-bill-of-materials-components/ — Moveo BOM walkthrough.

## Thor (AngelLM)

- https://github.com/AngelLM/Thor — **~1.5k★, CC BY-SA 4.0**, latest tag v2.1 (Sep 2021), 354 commits; Discord + forums; FreeCAD/KiCAD/GRBL.
- http://thor.angel-lm.com/ — 6-DOF (yaw-roll-roll-yaw-roll-yaw), ~625 mm tall, ~750 g, **3D-printed gears + GT2 belts**, <€350, 30+ builds in 17 countries.
- https://hackaday.io/project/12989-thor — Hackaday project page (community/maturity).
- https://www.thingiverse.com/thing:1743075 — Thor STLs (fully printable).

## Arctos

- https://blog.arduino.cc/2023/05/09/build-your-own-high-quality-arctos-robot-arm/ — overview (6-DOF, Arduino-based).
- https://hackaday.com/2023/05/08/arctos-robotics-build-a-robot-arm-out-of-3d-printer-spares/ — **NEMA17/23, GT2 belts, cycloidal gearboxes, Arduino Mega + CNC shield, ~3 kg PLA, 600 mm reach, 2 kg payload claim, ~$326+; CAD sold (€39.95) not open**, GRBL firmware open.
- https://www.robotshop.com/products/arctos-robotics-arctos-6-dof-diy-robotic-arm-kit-self-assembly-600mm-reach-2kg-payload-arduino-esp32-ros-compatible — 600 mm reach, 2 kg payload, Arduino/ESP32/ROS.
- https://github.com/Arctos-Robotics — org repos: ROS (~93★, May 2024), Arctos-grbl-v0.1 (~67★, Jun 2024), arctosgui (ROS1/MoveIt via CAN, ~29★, Mar 2025), RoboDK, MATLAB FK, **CLMD closed-loop motor driver (Nov 2025)** — active 2024–2025; **CAD not in the open repos**.

## EEZYbotARM (MK1/MK2/MK3)

- https://www.instructables.com/EEZYbotARM-Mk2-3D-Printed-Robot/ — MK2: 4-axis, servo-driven (MG946R + SG90), ABB IRB460 1:7 linkage.
- https://github.com/meisben/easyEEZYbotARM — Python+Arduino control lib w/ **3D IK for Mk1/Mk2**.
- https://cults3d.com/en/3d-model/tool/eezybotarm-mk3 and https://www.thingiverse.com/thing:2838859 — MK3 (stepper variant), free STLs; small scale, low payload.
- https://store.roboticsbd.com/robotics-parts/1163-... — MK1: payload ~5 g (marble), MG90S servos; very cheap.
- (search) MK3 created to swap servos→**economic steppers**; steppers found "weak," vertical-arm transmission reworked (unipolar→bipolar); ~3–4 DOF, tiny payload.

## Dummy-Robot (peng-zhihui)

- https://github.com/peng-zhihui/Dummy-Robot — **~15.1k★**, last activity ~Feb 2022; 6 joints; **20/42/57 steppers, closed-loop + CAN**, STM32/FreeRTOS, REF core board; original **CNC-machined**, planned 3D-print "Youth" version w/ cycloidal reducer; docs **in Chinese**; C-heavy.
- https://hackaday.com/2022/02/21/dummy-the-robot-arm-is-not-so-dumb/ — Hackaday writeup (one-maker project, advanced).

## WLkata Mirobot

- https://www.wlkata.com/products/wlkata-best-6-axis-stem-educational-robot-arm-kit — 6-axis educational product, open API/firmware (Arduino/GRBL-based).
- https://ozrobotics.com/shop/wlkata-mirobot-6-axis-mini-industrial-robot-for-education/ — "open source 6-axis," 0.2 mm repeatability, steppers; **commercial assembled product, not a from-BOM DIY arm**.
- https://lin-nice.github.io/mirobot_gitbook_en/13-wlkata.html — Mirobot spec/working-principle docs; ~150 g payload.

## Faze4 (PCrnjak)

- https://github.com/PCrnjak/Faze4-Robotic-arm — fully 3D-printable 6-axis; **3× NEMA23, 2× NEMA17, 1× NEMA14; cycloidal gearboxes (J1–J5) + planetary (J6)**; ~1000 parts; open design.
- https://faze4-robotic-arm-docs.readthedocs.io/en/latest/About_faze4.html — official docs (build quality signal).
- https://hackaday.com/2020/08/14/robotic-arm-sports-industrial-design-3d-printed-cycloidal-gears/ — Hackaday feature; low-backlash 3D-printed cycloidals.
- https://source-robotics.com/blogs/blog/faze4-robotic-arm-3d-printed-cycloidal-drives-in-robotics — design writeup; ~$1,000–1,500 cost class.

## Roundups / comparisons / context

- https://circuitdigest.com/articles/top-10-opensource-robotic-arms-for-beginners — "top 10" list (note: **servo-driven arms only**; does not cover the stepper arms — used to confirm scope boundary).
- https://github.com/adafruit/awesome-open-source-robotic-arms — curated awesome-list (discovery of additional repos).
- https://www.printables.com/model/611889-faze4-robotic-arm — Faze4 on Printables (community/maturity).
