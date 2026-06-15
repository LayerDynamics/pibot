# Agent 1 Findings — Enumeration of Open-Source STEPPER-Motor Robot Arms on GitHub

**Facet:** The "list them" core — enumerate the open-source, stepper-motor-driven robot
arm projects on GitHub, with concrete per-project metadata.

**Method / provenance:** Star counts, last-commit dates (`pushed_at`), licenses, and
archived status were pulled from the **GitHub REST API** (`api.github.com/repos/...`) on
**2026-06-15** for every repo where a canonical repo exists — these are marked
**API-verified**. DOF / motor-type / controller facts come from repo READMEs, project
sites, or secondary sources (Hackaday, vendor pages) and are marked **secondary** where
the API doesn't carry them. Star counts are point-in-time and shift daily — treat all as
**approx**.

> **Date note:** A few repos show a `pushed_at` in 2026 (e.g. `ar4_ros_driver`,
> `fabien-prog/6AR`, `mariohany01`). That is what the live API returned on the research
> date; reported verbatim, not inferred.

---

## Master table — well-known + verified projects

All star counts are **approx** (API snapshot 2026-06-15). "Last activity" = `pushed_at`
year from the API. "Prov." = provenance of the repo metadata (V = API-verified repo, the
DOF/motor facts are still secondary unless noted).

| # | Project | Canonical GitHub URL | Stars (approx) | DOF | Steppers / axes | Last activity | License | Prov. | One-liner |
|---|---------|----------------------|---------------:|-----|-----------------|---------------|---------|-------|-----------|
| 1 | **Annin Robotics AR4** (control SW) | https://github.com/Annin-Robotics/ar4-hmi | ~30 | 6 | 6× stepper (NEMA17/23), Teensy 4.1 + integrated encoders | 2025 (active) | Annin OSS Non-Commercial v1.1 (NOASSERTION) | V | Official AR4-MK3 control software; arm itself is the flagship hobby 6-DOF stepper arm |
| 2 | **AR4 ROS 2 driver** (community, ycheng517) | https://github.com/ycheng517/ar4_ros_driver | ~150 | 6 | same AR4 hardware | 2026 (active) | MIT | V | Most-used ROS 2 / MoveIt driver for the AR4 (MK1/2/3) |
| 3 | **AR4 ROS 2 driver** (official) | https://github.com/Annin-Robotics/ar4_ros_driver | ~15 | 6 | same AR4 hardware | 2026 (active) | MIT | V | Annin's own ros2_control driver |
| 4 | **Annin Robotics AR2** | https://github.com/Chris-Annin/AR2 | ~1,450 | 6 | 6× stepper, Arduino Mega (open-loop) | 2019 (stale) | none declared | V | The original Annin 6-axis stepper arm; AR3/AR4 are its successors |
| 5 | **Annin Robotics AR3** | *No canonical `Chris-Annin/AR3` repo (404)* — distributed via anninrobotics.com (Google-Drive zip). Community mirror: https://github.com/kentavv/annin_robotics_ar3 | mirror ~10 | 6 | 6× stepper, Teensy 3.5, added encoders (closed-loop) | mirror 2020 | mirror: none | V (mirror) | AR2→AR4 transitional model; **not on GitHub as a first-party repo** |
| 6 | **Thor** (AngelLM) | https://github.com/AngelLM/Thor | ~1,500 | 6 | 8 steppers driven (some joints doubled); GRBL-mod / RRF | 2025 (light activity) | CC-BY-SA-4.0 | V | Iconic fully-3D-printed 6-DOF stepper arm; 625 mm reach, ~750 g payload |
| 7 | **Thor-ROS** (AngelLM) | https://github.com/AngelLM/Thor-ROS | ~10 | 6 | Thor hardware | 2025 (active) | CC-BY-SA-4.0 | V | ROS 2 Humble + MoveIt2 stack for Thor (incl. "Asgard" web UI) |
| 8 | **BCN3D Moveo** | https://github.com/BCN3D/BCN3D-Moveo | ~1,880 | 5 | 5× stepper (NEMA17/23) + 1 servo gripper; Marlin on RAMPS/Mega | 2022 (stale) | MIT | V | Classic educational 5-DOF 3D-printed stepper arm; ~$400 BOM |
| 9 | **Dummy-Robot** (peng-zhihui) | https://github.com/peng-zhihui/Dummy-Robot | ~15,100 | 6 | 6× **closed-loop** stepper over **CAN**; STM32 "Ctrl" board, harmonic/cycloidal reducers | 2024 (stale) | none declared | V | Famous super-compact 6-axis arm; advanced closed-loop CAN stepper design (hard to replicate, no license) |
| 10 | **PAROL6** (PCrnjak / Source Robotics) | https://github.com/PCrnjak/PAROL6-Desktop-robot-arm | ~2,950 | 6 | 6× stepper, custom PAROL6 control board; Python API + ROS2/MoveIt | 2026 (active) | GPL-3.0 | V | Modern industrial-style desktop 6-DOF stepper arm; **successor to Faze4**, best-documented active project |
| 11 | **Faze4** (PCrnjak / Source Robotics) | https://github.com/Source-Robotics/Faze4-Robotic-arm *(redirect from PCrnjak/Faze4-Robotic-arm)* | ~860 | 6 | 6 steppers (3× NEMA23, 2× NEMA17, 1× NEMA14), Teensy 3.5; cycloidal+belt | 2025 (light) | CERN-OHL-S-2.0 | V | 3D-printed cycloidal-gearbox 6-axis stepper arm; predecessor to PAROL6 |
| 12 | **SmallRobotArm** (Skyentific) | https://github.com/SkyentificGit/SmallRobotArm | ~1,460 | 6 | 6× stepper, Arduino-class MCU; ~0.1 mm precision | 2019 (stale) | GPL-3.0 | V | Compact 6-DOF stepper arm from the Skyentific YouTube series |
| 13 | **Arctos (ROS package)** | https://github.com/Arctos-Robotics/ROS *(redirect from ArctosRobotics/ROS)* | ~90 | 6 | 6× stepper (NEMA17/23); GRBL-mod, Arduino Mega + CNC shield (open-loop) | 2024 (stale repo) | MIT | V | 6-axis 3D-printed arm "from 3D-printer spares"; rosserial→MoveIt. **Closed-loop CAN variant exists separately** |
| 14 | **Arctos GUI** | https://github.com/Arctos-Robotics/arctosgui | ~30 | 6 | Arctos hardware | 2025 (light) | none declared | V | CAN-bus + ROS1 MoveIt control GUI for Arctos v2 (closed-loop variant) |
| 15 | **EEZYbotARM** (easyEEZYbotARM, meisben) | https://github.com/meisben/easyEEZYbotARM | ~100 | 3–4 | **SERVO-based, NOT stepper** | 2023 (stale) | MIT | V | Popular tiny 3D-printed arm — **excluded: servo-driven** (see note) |

---

## Notable lesser-known / long-tail stepper repos (discovered via topic + keyword search)

All API-verified for stars/activity/license on 2026-06-15. These came from GitHub
topic/keyword sweeps (`robot-arm`, `6dof`, `stepper`, `nema17`) rather than the famous-name
list.

| Project | Canonical GitHub URL | Stars (approx) | DOF | Steppers | Last activity | License | One-liner |
|---------|----------------------|---------------:|-----|----------|---------------|---------|-----------|
| **RR1 — Real Robot One** (surynek) | https://github.com/surynek/RR1 | ~55 | 6 | NEMA23 + NEMA17, Arduino Due; custom split-ring planetary gearboxes; joint encoders | 2024 (semi-active) | AGPL-3.0 | DIY desktop 6-axis stepper arm with custom planetary gearing |
| **Open6X** (jk87) | https://github.com/jk87/Open6X | ~15 | 6 | NEMA17 + NEMA23 (+ MG996R servo gripper), Arduino Mega (open-loop), planetary gears | 2021 (stale) | MIT | Low-cost (~£400) off-the-shelf-parts 6-axis stepper arm |
| **6AR** (fabien-prog) | https://github.com/fabien-prog/6AR-Open-Source-6-Axis-Robot | ~30 | 6 | stepper/servo joints, Teensy 4.1 + RPi 5, JSON serial protocol, limit-switch homing | 2026 (active) | none declared | Teensy-4.1-driven 6-axis arm w/ JSON serial protocol (**beta, not yet released**) |
| **stepper-robot-arm** (Martin-Ansteensen) | https://github.com/Martin-Ansteensen/steppper-robot-arm | ~5 | 6 | NEMA17 + 28BYJ-48 + 2 servos, **Arduino Mega + RAMPS 1.4**, vision pick-and-place (RPi) | 2025 (active) | none declared | Camera-guided 6-joint stepper arm, Fusion360 + RAMPS |
| **6_DOF_Robot_Arm** (maxyuan6717) | https://github.com/maxyuan6717/6_DOF_Robot_Arm | ~5 | 6 | **SERVO, NOT stepper** — `Big_Arm.ino` uses `#include <Servo.h>` / `Servo servos[8]` / `.attach()`. **Exclude.** Master-slave radio teleop-mimic | 2020 (stale) | none declared | Student 6-DOF **servo** arm mirrored from a handheld controller (verified from `.ino` source) |
| **6-DOF-Robot** (mariohany01) | https://github.com/mariohany01/6-DOF-Robot | ~5 | 6 | stepper + RPi; full CAD→IK→MATLAB/Simulink→ROS+MoveIt+Gazebo pipeline | 2026 (active) | none declared | KUKA-style 6-DOF arm with a full simulation/ROS deployment pipeline |
| **Motor-driver-encoder-CAN-NEMA17** (RyanPaulMcKenna) | https://github.com/RyanPaulMcKenna/Motor-driver-encoder-CAN-NEMA17 *(redirect from .../Robotic-Arm)* | ~1 | 6 | NEMA17 + encoders + CAN | 2026 (active) | MIT | From-scratch 6-DOF arm: mechanical/electrical/firmware, CAN + encoders |

**Also seen in topic sweeps (not individually API-verified, listed for completeness, secondary source only):**

- `mo12896/bcn3d-moveo` — a Moveo implementation fork (Moveo is stepper). Secondary.
- `justbuchanan/eezybotarm-mk2-software`, `ronbuist/eezybot` — EEZYbotARM tooling
  (**servo**, flagged). Secondary.
- `hobofan/collected-robotic-arms` and `adafruit/awesome-open-source-robotic-arms` —
  curated lists, useful as discovery indexes (Adafruit's list is thin and surfaces mostly
  AR4 / Arctos / Reachy / Pedro). Secondary.

---

## Stepper vs. servo — the key distinction the user asked about

The user specifically wants **stepper** arms. The split in this landscape:

**Genuinely STEPPER-driven (the target set):** AR2 / AR3 / AR4, Thor, BCN3D Moveo (steppers
+ 1 servo gripper), Dummy-Robot (closed-loop stepper + CAN), PAROL6, Faze4, SmallRobotArm,
Arctos, RR1, Open6X, 6AR, and the long-tail repos above. NEMA17 and NEMA23 dominate;
NEMA14 appears on small wrist joints.

**SERVO-based — FLAG / EXCLUDE:** the entire **EEZYbotARM** family (mk1/mk2/mk3) is built
on hobby servos, not steppers. Also reclassified to servo after source inspection:
**maxyuan6717/6_DOF_Robot_Arm** — its `Big_Arm.ino` is `#include <Servo.h>` with eight
`Servo.attach()` channels, a master-slave teleop-mimic, **not** a stepper arm (it surfaced
in stepper keyword searches but is excluded). It shows up constantly in "open-source robot arm" searches
and is frequently mistaken for a stepper arm — it is not. Also servo-class and out of
scope: most "robot arm" Arduino-servo tutorials and the **Reachy/Pollen** arms (dynamixel
smart servos, not steppers).

**Within steppers, two sub-classes that matter for the PiBot controller axis:**

- **Open-loop step/dir steppers** (AR2/AR4 base, Thor, Moveo, Arctos open-loop, RR1,
  Open6X, SmallRobotArm, Martin-Ansteensen) — these are the ones that map most directly
  onto a 4× step/dir driver board like the Creality 4.2.2. AR4/Thor/Moveo each need **6
  drivers** (Moveo 5), so a single 4-driver board can't reach 6-DOF alone — a 2nd board or
  driver expansion is required.
- **Closed-loop / CAN steppers** (Dummy-Robot, Arctos closed-loop variant, parts of
  RyanPaulMcKenna) — these use per-joint encoders and CAN-bus smart-driver modules.
  Mechanically still steppers, but they do **not** drive off a plain step/dir 3D-printer
  board; flag these on the controller axis.

---

## Coverage notes / gaps (honest)

- **All 7 named "must-cover" projects were verified to exist and classified:** AR4/AR3/AR2
  (AR3 has **no first-party GitHub repo** — site-distributed, community mirrors only),
  Thor, BCN3D Moveo, Arctos, EEZYbotARM (confirmed **servo**, flagged), Dummy-Robot, and
  WLkata Mirobot. **Total enumerated: ~22 distinct repos** (15 in the main table + 7 in the
  lesser-known table), plus the curated-list/secondary references.
- **WLkata Mirobot:** the Mirobot is a *commercial* product whose firmware is described as
  "Arduino-based, open-sourced," but I found **no first-party firmware repo** on the
  `wlkata` GitHub org — only the Python SDK (`wlkata/mirobot-py`, ~12★, MIT, active 2025),
  ROS packages (`RosForMirobot-master`, `ROS2_WLKATA`), and STL models. So Mirobot is only
  *partially* open on GitHub (SDK/ROS/STL yes; core firmware not clearly in a repo). It is a
  stepper arm.
- **DOF/motor/controller facts** for the smallest long-tail repos rely on READMEs and
  search snippets (secondary); stars/dates/licenses for every repo with a canonical URL are
  API-verified.
- **Not deeply evaluated here (out of this facet):** payload/reach numbers, BOM cost,
  gearing detail, and the controller-compatibility scoring against the Creality 4.2.2 — that
  is the job of Agents 2–4. I surfaced controller/driver-count and closed-loop-vs-open-loop
  signals only enough to classify the stepper sub-class.
