# Agent 2 Sources — Controllers, Firmware & Stepper-Driver Hardware

Every URL consulted, with what it established and whether it was **fetched** (primary text
read via WebFetch) or **search snippet** (WebSearch result summary). Claims in
`Agent2Findings.md` rely on fetched primary sources where the cell is not marked
"unverified."

## AR4 (Annin Robotics)
- https://github.com/Annin-Robotics/ar4_ros_driver — **fetched**. Confirms **Teensy 4.1** main
  controller + **Arduino Nano** gripper, **6 joints (J1–J6)**, calibration/homing, serial via
  pyserial (`/dev/ttyACM0` Teensy, `/dev/ttyUSB0` Nano). Firmware in `annin_ar4_firmware`.
- https://github.com/Annin-Robotics/ar4_ros_driver/blob/main/README.md — **fetched**. Confirms
  Teensy 4.1 board selection for flashing, 6-axis, per-joint calibration. Exact serial wire
  format and driver chip not stated in README (firmware source only) → noted as such.
- https://github.com/Annin-Robotics/ar4-hmi — **fetched**. AR4-MK3 = six-axis, Teensy 4.1,
  encoder test files present (closed-loop calibration), pyserial host comms.
- Teensy 4.1 spec context (600 MHz Cortex-M7 with FPU) — general knowledge corroborated by the
  Annin FAQ snippet ("operates at 600 MHz needed for the robot arm kinematics").

## Annin AR2 / AR3 (precursors to AR4)
- https://github.com/Chris-Annin/AR2 — search snippet. **AR2 = 6-axis stepper robot on
  Arduino Mega**, open-loop, Gen2 control software.
- https://github.com/kentavv/annin_robotics_ar3 — search snippet. AR3 software.
- https://hackaday.com/2019/10/17/open-source-arm-puts-robotics-within-reach/ — search snippet.
  **AR2 = Arduino Mega, open-loop; AR3 adds encoders (closed-loop), moves motors+encoders to a
  Teensy 3.5 while an Arduino Mega handles I/O, grippers, servos**; belt-and-pulley.
- https://confluencerd.com/.../Annin-Robotics-AR2-AR3-robotic-arm-bill-of-materials/ and
  anninrobotics forum — search snippets. **DM542T external stepper drivers** (PUL/DIR 4–5 V).
- Establishes AR2 as the **closest Annin arm to the printer-board world** (open-loop step/dir +
  custom ASCII serial), and AR3 as Teensy-3.5-coprocessor-dependent for encoders.

## PAROL6 (Source Robotics) — dedicated STM32 arm board (reference point)
- https://source-robotics.github.io/PAROL-docs/page3_1/ and
  https://www.tindie.com/products/sourcerobotics/parol6-robot-control-board/ — search snippets.
  **Custom control board: STM32F446RE (Cortex-M4, FPU) + 6× TMC5160 step/dir drivers**, 6 limit
  sensors, CAN, USB, ESTOP, 64MB flash, ST-Link/SWD programming.
- https://github.com/PCrnjak/PAROL6-Desktop-robot-arm — search snippet. Open-source firmware
  (TMCStepper lib), GUI, STLs; 6-axis, 400 mm reach. Included as "what a purpose-built STM32
  arm board looks like" vs a repurposed 4.2.2.

## Thor (AngelLM)
- https://github.com/AngelLM/Thor — search snippet. 6 DOF (yaw-roll-roll-yaw-roll-yaw), ~625 mm,
  750 g payload.
- https://github.com/AngelLM/Thor/wiki/FAQ — **fetched**. Confirms **Arduino Mega + modified
  GRBL**, actuators wired to a **custom PCB**; some users substitute commercial boards.
- https://github.com/AngelLM/ThorControlPCB — search snippet. RAMPS-1.4-based Arduino Mega
  shield, **up to 8 A4988 stepper drivers**, 8 endstops, tool PWM.
- http://thor.angel-lm.com/documentation/electronics/ — **fetch attempted, ECONNREFUSED**
  (site down at fetch time); board/driver details obtained from the FAQ + ControlPCB repo
  instead. Dual-motor articulation ⇒ ~7 drivers is inferred from the 8-socket shield + 6-DOF
  layout (flagged in findings).
- https://www.thingiverse.com/thing:1743075 — fetch returned 403; not used.

## BCN3D Moveo
- https://github.com/BCN3D/BCN3D-Moveo — **fetched**. Confirms **Marlin** firmware
  (`FIRMWARE/Marlin_BCN3D_Moveo`), Arduino-controlled, open-source 3D-printed educational arm.
- https://github.com/BCN3D/BCN3D-Moveo/blob/master/FIRMWARE/Marlin_BCN3D_Moveo/Configuration_adv.h
  — search-indexed; confirms Marlin config (RAMPS pin model, dual-axis on 2nd extruder socket).
- BOM/motor search results (Issue #7, #3; Scribd BOM; esorensen.com) — search snippets.
  Establish **NEMA 23 (SM57HT112-3004A, 3 A, 28 kg·cm)** on the heavy joint and **NEMA 17 w/
  5:1 planetary** elsewhere; 5 DOF + servo gripper; ~$400 build. This is the NEMA23/external-
  driver discriminator.
- https://www.jesseweisberg.com/moveo-with-ros — search snippet. Mega 2560 + RAMPS 1.4, all
  joints stepper except servo gripper; ROS integration precedent.

## Arctos
- https://arctosrobotics.com/docs/ — **fetched**. **Current** docs: recommended **closed-loop =
  CANable v2 USB-CAN + MKS SERVO42D ×4 + SERVO57D ×2** (closed-loop steppers over **CAN**);
  open-loop alt = **Arduino Mega 2560 + CNC Shield V3 + TMC2209** with **GRBL**. 6 DOF, NEMA23
  (X/Y) + NEMA17 (Z/A/B/C). Host: G-code (open-loop), CAN (closed-loop), ROS1/ROS2.
- https://hackaday.com/2023/05/08/arctos-robotics-build-a-robot-arm-out-of-3d-printer-spares/
  — **fetched**. **Original** Arctos: **Arduino Mega2560 + CNC shield + A4988/DRV8825**,
  **modified GRBL**, 6 DOF, NEMA17/23, designed from 3D-printer/CNC spares; encoders for
  closed-loop noted in build manual.
- https://github.com/Arctos-Robotics/arctosgui — search snippet. GUI controls arm over **CAN
  bus + ROS1 MoveIt**; supports Arduino Mega or CANable adapter.

## peng-zhihui Dummy Robot
- https://github.com/peng-zhihui/Dummy-Robot — search snippets + indexed paths. Firmware tree:
  `Core-STM32F4-fw/` (main, FreeRTOS) and `Ctrl-Step-Driver-STM32F1-fw/` (per-motor stepper
  driver). ESP32 for Wi-Fi.
- https://hackaday.com/2022/02/21/dummy-the-robot-arm-is-not-so-dumb/ — search snippet. Custom
  **closed-loop stepper controller mounted to each motor**, harmonic drive, STM32 + ESP32.
- Custom **Ctrl-Step** driver adds **CAN bus**, supports 20/42/57 steppers; references XDrive
  (https://github.com/unlir/XDrive) closed-loop STM32 driver — search snippets. ⇒ bespoke
  distributed CAN/FOC, not a single step/dir board.

## EEZYbotARM
- https://github.com/meisben/easyEEZYbotARM — search snippet. Python+Arduino control,
  **PWM servo** signals (MG996R-class), kinematics for MK1/MK2. Confirms it is a **servo** arm.
- https://github.com/SphaeroX/EEZYbotARM-ESP32-Control — search snippet. ESP32 servo control
  (MK2/MK3).
- Hackster CNC-shield stepper variant — search snippet. Non-standard stepper retrofit exists
  but is not the canonical design.

## WLkata Mirobot
- https://github.com/wlkata — search snippet. Official org; ROS2 packages, Python SDK.
- https://github.com/wlkata/mirobot-py — search snippet. **G-code over serial**; closed
  commercial firmware/board (STM32-class internals **unverified** — not open hardware).

## Core "3D-printer STM32 board → 6-DOF arm" question
- https://github.com/grblHAL/Controllers and grblHAL STM32 ports — search results. grblHAL on
  **STM32F103** sustains **~250 kHz/axis (3-axis)** and **~150 kHz/axis (6-axis)**; supports up
  to **6 axes**. Key evidence that F103 step generation is not the bottleneck.
- https://github.com/sasan18s/grbl-stm32-6axis — search snippet. GRBL 1.1f ported to
  STM32F103/F407, 6-axis.
- https://klipper.discourse.group/t/six-axis-robots/668 and /t/6-axis-compatible/4099 — search
  snippets. Community XYZ→XYZABC 6-axis Klipper mods on printer MCUs (FYSETC Spider/SKR).
- https://www.airspayce.com/mikem/arduino/AccelStepper/classMultiStepper.html — search snippet.
  `MultiStepper` = constant-speed-only coordinated moves (no accel/decel); MULTISTEPPER_MAX = 10.
- https://www.airspayce.com/mikem/arduino/AccelStepper/ + Arduino-forum threads — search
  snippets. AccelStepper ~4 kSteps/s on 16 MHz AVR; ~30–100 kSteps/s on STM32-class MCUs.
- https://github.com/gin66/FastAccelStepper — search snippet. Higher-rate alternative
  (timer/ISR-driven) for AVR/ESP32/SAM — supports the "drive steps from a HW timer" point.
- https://github.com/dzid26/StepperServoCAN — search snippet. **Separate** project
  (STM32F103C8 closed-loop CAN stepper); noted only to avoid conflating it with Arctos/Mirobot.
