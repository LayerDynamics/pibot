# Expanded Searches — Open-Source Stepper Robot Arms on GitHub

**Research topic (verbatim):** "stepper robot arms that are on github — list them, and their compatibility and viability"

**Purpose:** Surface and evaluate open-source, stepper-motor-driven robot arms on GitHub for the **PiBot** project. The downstream research must score each candidate on three axes:

- **(a) Controller compatibility** — works on a Creality 4.2.2-class board: STM32F103RET6 (512KB flash, 72MHz Cortex-M3, **no FPU**), 4 onboard stepper drivers (X/Y/Z/E), endstop headers, 24V supply. 5–6 DOF needs a 2nd board or driver expansion.
- **(b) Software compatibility** — firmware stack (Arduino/STM32duino, Marlin, Klipper, GRBL/grblHAL), ROS2/MoveIt support, reusable IK/kinematics for a Python "solver seam" (ikpy / DH params / URDF), and protocol (G-code vs simple ASCII serial — PiBot uses an ASCII line+CRC protocol @115200).
- **(c) Viability** — DOF, payload, reach, steppers/gearing (belt, planetary, harmonic, cycloidal), 3D-printable vs machined, BOM cost, build difficulty, maturity (stars / last commit / license).

> **Note for the research agents:** Do not just confirm a project exists — pull the *controller and driver count* (tightest constraint), the *firmware/control stack*, and the *viability numbers* for each. A Creality 4.2.2 has only 4 drivers and no FPU, so any arm that mandates RAMPS/Mega, Teensy 4.x, a custom PCB, or CAN/closed-loop steppers should be flagged on the controller axis.

---

## Cluster 1 — Enumerate the well-known open-source stepper robot-arm repos

**Why it matters:** Establishes the canonical candidate list. These are the projects with the most documentation, community, and reusable design/IK assets — the baseline every other finding is compared against.

```text
Annin Robotics AR4 robot arm github
Annin Robotics AR3 open source robot arm github
Annin Robotics AR2 robot arm repository
Thor open source robot arm AngelLM github
BCN3D Moveo open source robotic arm github
Arctos robotics open source robot arm github
EEZYbotARM mk1 mk2 mk3 github
Dummy robot CtrlRobot peng-zhihui github
WLkata Mirobot open source firmware github
open source 6 DOF 3D printable robot arm github stepper
"robot arm" stepper open source github DH parameters
```

---

## Cluster 2 — GitHub-scoped discovery of lesser-known repos

**Why it matters:** Beyond the famous names there is a long tail of active stepper-arm repos. GitHub topic/keyword scoping surfaces them with stars and last-commit signals so we can judge maturity and avoid abandoned projects.

```text
site:github.com robot-arm stepper 6dof
site:github.com topics robotic-arm stepper open-source
github.com topics/robot-arm stars
github topic open-source-robot-arm stepper motor
site:github.com "robot arm" 6dof stepper marlin OR grbl OR klipper
github search robotic-arm language:Python ikpy stepper
github.com "5 DOF" OR "6 DOF" stepper robot arm URDF
site:github.com awesome robot arm open source list
github stepper robot arm "last commit 2025" OR "2024" active
```

---

## Cluster 3 — Controllers & firmware each project requires (TIGHTEST CONSTRAINT)

**Why it matters:** This is the make-or-break axis. PiBot's controller is an STM32F103 (Creality 4.2.2) with **4 drivers and no FPU**. Most open arms assume RAMPS + Arduino Mega, Teensy 4.x, ESP32, or a bespoke PCB. We need to know, per arm, *what board it runs on, how many stepper drivers it needs, and whether it depends on closed-loop/CAN steppers* — because that determines whether it ports to a 4.2.2 (and whether 5–6 DOF forces a 2nd board).

```text
AR4 controller Teensy 4.1 stepper driver count firmware
AR3 AR4 Arduino Mega RAMPS stepper drivers required
Thor robot arm RAMPS Arduino Mega firmware controller
BCN3D Moveo RAMPS 1.4 Arduino Mega controller drivers
EEZYbotARM controller Arduino servo vs stepper
Arctos robot arm controller board ESP32 OR STM32 firmware
open source robot arm STM32 controller firmware github
robot arm Creality "4.2.2" OR STM32F103 3D printer board reuse stepper
open source robot arm Klipper OR Marlin OR grblHAL firmware
robot arm closed loop stepper CAN driver open source
how many stepper drivers does a 6 DOF arm need second board expansion
3D printer mainboard repurpose robot arm stepper motors reddit
```

---

## Cluster 4 — Software / control stacks (ROS2, MoveIt, protocols)

**Why it matters:** PiBot has a ROS2 bridge and a swappable solver seam, and speaks a simple ASCII serial protocol — not G-code. We need to know which arms ship ROS/ROS2/MoveIt packages (reusable directly) versus those locked to G-code/Marlin or proprietary GUIs (would need a protocol shim to PiBot's ASCII line+CRC link).

```text
AR4 ROS2 MoveIt package github ar4_ros_driver
AR3 ROS MoveIt support repository
BCN3D Moveo ROS MoveIt URDF package github
open source robot arm ROS2 MoveIt2 stepper github
robot arm gcode vs serial protocol control stepper
Thor robot arm control software GUI firmware protocol
robot arm Python serial control ikpy stepper github
open source robot arm ROS2 driver stepper joint position velocity
Arctos robot arm software ROS MoveIt GUI
convert robot arm gcode controller to custom serial protocol
```

---

## Cluster 5 — Kinematics / IK reusability in Python (DH, URDF, ikpy)

**Why it matters:** PiBot's solver seam wants reusable forward/inverse kinematics. The cheapest path is an arm that publishes DH parameters or a clean URDF we can feed to ikpy/MoveIt. We need to know which projects expose IK we can lift versus those with hard-coded or undocumented kinematics.

```text
AR4 DH parameters inverse kinematics github
AR4 URDF file ros description package
BCN3D Moveo URDF inverse kinematics ikpy python
Thor robot arm DH parameters kinematics document
open source robot arm URDF download github 6dof
ikpy robot arm 6 DOF inverse kinematics example github
robot arm DH parameters table open source stepper
python inverse kinematics library robot arm URDF MoveIt
6 DOF robot arm forward kinematics open source repository
robotics toolbox python peter corke robot arm URDF import
```

---

## Cluster 6 — Viability: DOF, payload, reach, gearing, cost, maturity, license

**Why it matters:** Even a controller- and software-compatible arm is a poor choice if it can't lift anything, costs thousands, or is abandoned. This axis pulls the hard numbers — DOF, payload, reach, gearing type (belt / planetary / harmonic / cycloidal), printable-vs-machined, BOM cost — plus the maturity signals (stars, last commit, license) that predict long-term support.

```text
AR4 payload reach DOF specifications BOM cost
AR3 vs AR4 payload reach build cost comparison
BCN3D Moveo payload reach 3D printed cost BOM
Thor robot arm payload reach gearing 3D printable cost
EEZYbotARM payload reach cost mk2 mk3 specifications
open source robot arm harmonic drive vs cycloidal vs planetary gearing
cheapest open source 6 DOF robot arm BOM cost 2025
open source robot arm license MIT GPL CC commercial use
open source robot arm 3D printable vs machined parts payload
robot arm github stars last commit maintained 2025 2026
Arctos robot arm payload reach cost build difficulty
open source robot arm belt drive vs gearbox backlash stepper
```

---

## Cluster 7 — Comparisons, roundups, and community knowledge

**Why it matters:** Listicles, forum threads, and build logs aggregate hard-won real-world experience — which arms actually get built, where they fail, and how builders adapt controllers/firmware. These sources frequently name repos we'd otherwise miss and reveal practical compatibility gotchas the READMEs omit.

```text
best open source robot arm 2025 stepper 3D printable
best open source robot arm 2026 comparison roundup
open source 6 DOF robot arm comparison AR4 Thor Moveo Arctos
reddit r/robotics open source stepper robot arm recommendation
reddit r/3Dprinting robot arm 3D printed which one to build
hackaday open source robot arm stepper build
"AR4" vs "Thor" vs "Moveo" which robot arm to build forum
open source robot arm comparison table DOF payload cost
hackaday.io robotic arm project stepper STM32
youtube open source robot arm build review AR4 Arctos honest
```

---

## Coverage map (self-check)

| Required coverage area | Cluster(s) |
| --- | --- |
| 1. Enumerate well-known repos (AR4/3/2, Thor, Moveo, Arctos, EEZYbotARM, Dummy/CtrlRobot, Mirobot, etc.) | 1 |
| 2. GitHub-scoped discovery of lesser-known repos (topics/keywords, stars/activity) | 2 |
| 3. Controllers & firmware per project; STM32 / 3D-printer-board compatibility; driver count; closed-loop/CAN | 3 |
| 4. Software/control stacks — ROS/ROS2/MoveIt, IK libs, G-code vs serial protocol | 4 |
| 5. Kinematics/IK reusability in Python (DH params / URDF) | 5 |
| 6. Viability — BOM cost, DOF, payload/reach, gearing, printable/machined, license, maturity/activity | 6 |
| 7. Comparisons / roundups ("best open source robot arm 2024/2025/2026") | 7 |
