# Agent 4 Findings — Curated Lists + Lesser-Known Named Stepper Arms (STEP check)

**Facet:** Mine aggregator/"awesome" lists and lesser-known named open-source
**stepper** robot arms, verifying real downloadable **STEP** (`.step`/`.stp`) geometry.
Servo arms are out of scope. STL-only / SLDPRT-only / Inventor-source-only do not count
as a STEP win.

**Method:** Fetched the named curated indexes, mined their arm links, then verified each
candidate's motor type and CAD format against **primary sources** — the GitHub Trees API
(`/git/trees/<branch>?recursive=1`) for exact file extensions, plus repo READMEs and the
project's own Hackaday/landing page for motor type. STEP presence is asserted only where
the API actually returned `.step`/`.stp` paths. Motor type is asserted only where a
primary page states it.

**Verdict (one line):** The only NEW *arm-level* clean STEP-having **stepper** arm the
curated lists surfaced is **BetaBots** (verified). Annin-Robot-Project ships a zipped STEP
but is the AR2 predecessor (geometry redundant with the already-cloned AR2/AR3/AR4
lineage). Mantis-Robot-Arm has STEP only for its gripper accessory; the arm body is
Inventor-source-only. Everything else on the lists was either servo, STL-only, or already
in the cloned set.

---

## NEW candidates worth cloning

| Arm | Surfaced by (curated list) | Canonical URL | STEP present? | DOF | Stepper vs servo | License | Already cloned? |
|-----|----------------------------|---------------|---------------|-----|------------------|---------|-----------------|
| **BetaBots Robot Arm** (ChaozLabs) | hobofan/collected-robotic-arms (listed there as "STEP, STL") | https://github.com/4ndreas/BetaBots-Robot-Arm-Project | **YES — verified.** 9 `.stp` files in `Green/step/` + `ThreeFingerGripper/step/` (full-assembly `RobotV4.stp` + RotBase, Shoulder, Elbow, forearm, Wrist, WristRot, GripperMount, 3-finger gripper) | 6 | **Stepper** (verified via Hackaday project 3800: NEMA24 on joints 1–2, NEMA17 on joints 3–4; joint 5 is a HerkuleX smart servo; TB6560 drivers) | GPL-3.0 | **NO — NEW** |

### BetaBots verification detail (primary sources)
- STEP files (GitHub Trees API, branch `master`):
  `Green/step/RobotV4.stp`, `Elbow.stp`, `forearm.stp`, `GripperMount.stp`, `RotBase.stp`,
  `Shoulder.stp`, `Wrist.stp`, `WristRot.stp`, and `ThreeFingerGripper/step/3_finger_gripper.stp`.
  A dedicated `step/` folder (not just one stray export) = a real neutral-CAD drop.
- Inventor source (`.iam`/`.ipt`) also present under `Green/Inventor/` — the `step/` folder
  is the neutral export of that.
- Motors: README points to Hackaday project **3800** (ChaozLabs); that page states
  "Joint one and two will be Nema24 … Joint 3 and 4 Regular Nema17 stepper and for the 5
  joint a HerkuleX DRS-0101" and "5 × … TB6560 Stepper Motor Driver Boards." Primary arm
  motion is stepper-driven → in scope.

---

## Marginal / partial — flagged, not a clean arm STEP win

| Arm | Surfaced by | Canonical URL | STEP present? | DOF | Stepper vs servo | License | Already cloned? |
|-----|-------------|---------------|---------------|-----|------------------|---------|-----------------|
| **Annin-Robot-Project** (Chris Annin original) | "github robot arm stepper step folder" sweep | https://github.com/Chris-Annin/Annin-Robot-Project | STEP present but **packaged as `Step files/Step files.zip`** (zip contents NOT opened/verified). SolidWorks `.SLDPRT` source also present; loose parts are `STL files/*.STL`. | 6 | **Stepper** (repo desc "6 axis stepper motor robot") | GPL-3.0 | **Effectively yes — this is the AR2 predecessor.** AR2/AR3/AR4 already cloned. Geometry is the same arm family → **likely redundant; do not waste a clone.** |
| **Mantis-Robot-Arm** (4ndreas, same author as BetaBots) | hackaday "named stepper arm" sweep | https://github.com/4ndreas/Mantis-Robot-Arm | **Arm body = Inventor `.ipt`/`.iam` only (no `step/` folder).** Only `.stp` in the repo is the gripper accessory: `MantisGripper/step/GripperM120_2.stp`. → STEP = gripper only, NOT the arm. | ~6 | Stepper (3D-printable arm by the BetaBots author) | **NOASSERTION** (LICENSE.md present but not an SPDX-recognized license) | NO, but **not a clean STEP arm** — body is Inventor-source-only |

---

## EXCLUDED — checked and ruled out (with reason)

| Arm | Source list | URL | Reason excluded |
|-----|-------------|-----|-----------------|
| reBot-DevArm | adafruit awesome list / search | https://github.com/Seeed-Projects/reBot-DevArm | **Servo** (Robstride/Damiao/Mota smart-servo motors). Has STEP, but servo → out of scope. |
| Pedro 2.0 | adafruit awesome list | https://github.com/almtzr/Pedro | **Servo** (4× mini servo 360°) + **STL only**. |
| EvoArm | github.com/topics/robot-arm | https://github.com/AliShug/EvoArm | **Servo** (Dynamixel AX-12/18A + XL-320 smart servos). 3+2 DOF. |
| Alejo Restrepo "6-DOF Stepper Robot Arm" | search (alerest285.github.io) | https://github.com/alerest285/robotic_arm | Repo's own abstract: "using **servo motors** as the main actuators." Out of scope despite the page title. |
| armour (paulmorrishill) | github topics / search | https://github.com/paulmorrishill/armour | Stepper (A4988) but **3-DOF Dobot-style** and **STL only** (no STEP). |
| RyanPaulMcKenna arm (renamed `Motor-driver-encoder-CAN-NEMA17`) | search | https://github.com/RyanPaulMcKenna/Motor-driver-encoder-CAN-NEMA17 | NEMA17 stepper, but repo has **no CAD geometry at all** (CAN motor-driver firmware/electronics only). Nothing to harvest. MIT. |
| cybot_arduino (CyBot cycloidal control code) | hackaday/search | https://github.com/quartit/cybot_arduino | Arduino stepper control code only — **no CAD files** in repo. GPL-3.0. |
| circuitdigest "Top 10 Open Source Robotic Arms 2025" entries | roundup article | https://circuitdigest.com/articles/top-10-opensource-robotic-arms-for-beginners | All 10 are **servo** (SG90/MG995) hobby arms; only 1 even mentions STEP. None in scope. |
| Adafruit-list misc: DOBOT M1/Magician, uArm, Niryo One, 7Bot, Bender, Lite Arm i2 | hobofan + adafruit lists | (commercial / Thingiverse links) | Commercial products or servo/STL hobby arms — no open stepper-arm STEP. |

---

## Already-cloned arms re-surfaced by the lists (confirming coverage, not new)

The curated lists and roundups repeatedly returned arms **already in the cloned set**, which
confirms the prior sweeps were thorough: **Thor, BCN3D Moveo, AR2, AR3, Faze4, RR1,
SmallRobotArm, Martin-Ansteensen (steppper-robot-arm), 6AR, Open6X, Arctos.** No new STEP
geometry to gain from these — they are listed here only to show the lists were fully mined.

---

## Bottom line for the "download all that have STEP" goal

1. **Clone now (NEW, verified):** `4ndreas/BetaBots-Robot-Arm-Project` — 9 `.stp` files,
   6-axis stepper, GPL-3.0.
2. **Skip as redundant:** `Chris-Annin/Annin-Robot-Project` — zipped STEP but it's the
   AR2 predecessor; AR2 is already cloned (same arm family).
3. **Gripper-only / not an arm STEP win:** `4ndreas/Mantis-Robot-Arm` — arm body is
   Inventor-source-only; only the gripper has STEP.
