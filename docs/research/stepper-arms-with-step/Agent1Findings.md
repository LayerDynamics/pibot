# Agent 1 Findings — GitHub repos: open-source STEPPER arms that ship real STEP CAD

**Facet:** GitHub repositories of open-source **stepper-motor** robot arms that ship real
`.step`/`.stp` (B-rep neutral) CAD files. Goal = NEW arms beyond the already-cloned set.

**Method:** Authenticated `gh` CLI (account `LayerDynamics`). Discovery via
`gh search repos` + `gh search code`, list-mining of the two curated lists
(`adafruit/awesome-open-source-robotic-arms`, `hobofan/collected-robotic-arms`).
**Verification** of every candidate via the GitHub trees API
(`gh api repos/<r>/git/trees/HEAD?recursive=1` → grep `\.(step|stp)$`) **plus** a
motor-type check (README keywords + the CAD tree's own motor part filenames / the
`*.ipt` `Servo`/`Nema` parts). A hit only counts if it is **(a) genuinely stepper** and
**(b) has a downloadable STEP/STP** I actually saw in the tree.

## Headline result (honest intersection)

- **NEW ∩ stepper ∩ verified loose STEP in-tree = 1 repo: `4ndreas/BetaBots-Robot-Arm-Project`.**
- The other STEP-having arms I verified turned out to be **SERVO** (Dynamixel / SG90 /
  MG996R / mini-servo) and are therefore **out of scope** — listed below as flagged
  negatives, per the task's "flag any that turn out servo" rule.
- Several genuinely-stepper arms I found ship **no loose STEP** in-tree (and no STEP in
  release assets where checkable) — also listed, so the team doesn't re-chase them.

## Table

| Repo (URL) | NEW? | STEP present (yes/no/unverified) + where | DOF | Stepper | License | Note |
|---|---|---|---|---|---|---|
| [4ndreas/BetaBots-Robot-Arm-Project](https://github.com/4ndreas/BetaBots-Robot-Arm-Project) | **YES** | **YES** — exactly 9 `.stp` at HEAD: 8 in `Green/step/` (Elbow, Shoulder, Wrist, WristRot, RotBase, forearm, GripperMount, RobotV4) + `ThreeFingerGripper/step/3_finger_gripper.stp`. (A `Blue/step/` folder exists but holds only `README.md` — no STEP committed there.) | 6-DOF | **YES** — Inventor CAD has `Nema11.ipt`, `Nema17.ipt`, `Nema17 Geared.ipt`, `Nema23.ipt`, `GearedStepper_RotBase*.ipt`, `StepperBase`, `StepperMotorDriverMount.ipt` | GPL-3.0 | 386★. Best new find. 3D-printable, geared NEMA17/23. Inventor source + neutral STP. The `hobofan/collected-robotic-arms` list independently records its hardware formats as "STEP,STL" — corroborates the STEP claim. (Note: **BCN3D-Moveo, already cloned, is "originally based on BetaBots"** — so BetaBots is the ancestor design, not a Moveo derivative.) **Recommend clone (geometry only).** |
| [mattweidman/Manuel-1.0](https://github.com/mattweidman/Manuel-1.0) | new, but OUT | YES — 49 `.step` under `models/step/{elbow,gripper,...}` | 6-DOF + gripper | **NO — SERVO** (Dynamixel X-series, backdrivable) | MIT | 162★. STEP-rich but **servo** → out of scope. Geometry only could be reused, but it's a servo arm; flagged. |
| [Jeffh1505/Robotic-Arm](https://github.com/Jeffh1505/Robotic-Arm) | new, but OUT | YES — 5 `.STEP` in `STEP Files/` (incl. a "Servo Gear.STEP") | ~5/6 | **NO — SERVO** (Pi Pico + SG90 + PCA9685) | MIT | "MechArm". Servo → out of scope. |
| [hrushikeshrv/charm](https://github.com/hrushikeshrv/charm) | new, but OUT | YES — 9 `.stp` in `data/cad/step/` (Arm01/02, Base, Waist, Gripper, gears) | chess arm | **NO — SERVO** (CAD has `Servo Motor MG996R.ipt`, `Servo Motor Micro 9g.ipt`) | GPL-3.0 | Servo → out of scope. |
| [Seeed-Projects/reBot-DevArm](https://github.com/Seeed-Projects/reBot-DevArm) | new, but OUT | YES — `.step` under `hardware/reBot_B601_DM/3D_Printed_Parts/` (mounts/gripper) | 6-DOF + gripper | **NO — SERVO** (CAN servos: Damiao/Robostride/etc.) | CERN-OHL-W-2.0 (hw) / Apache-2.0 (sw) | Servo → out of scope. |
| [almtzr/Pedro](https://github.com/almtzr/Pedro) | new, but OUT | no (in-tree); STL-oriented | small arm | **NO — SERVO** (4x 360° mini servos) | Apache-2.0 | 136★. Servo → out of scope. |
| [youssef14sawan/Aegis-V (Cycloidal)](https://github.com/youssef14sawan/Aegis-V-A-High-Torque-Cycloidal-Robotic-Arm-with-CV-Guided-Autonomy) | new | **NO** loose STEP in-tree; no release assets | 5-axis | YES (stepper, "motor steps", cycloidal) | none stated | Genuinely stepper but no STEP CAD published (yet). Not usable for geometry reuse. |
| [thnsmmrs/cycloidal-robot-arm](https://github.com/thnsmmrs/cycloidal-robot-arm) | new | **NO** loose STEP; no releases | modular | YES (ESP32 + DM542 stepper driver, cycloidal) | none | Stepper but no STEP CAD in tree. |
| [gouldpa/Triple-Cycloidal-Robot-Arm-Proto-2](https://github.com/gouldpa/Triple-Cycloidal-Robot-Arm-Proto-2) | new | **unverified** — only `Tri_proto_2.zip` / `..._rev1.zip` in tree (may contain STEP inside zip); no loose STEP, no releases | triple-cycloidal | likely stepper (NEMA17, cycloidal — per Hackaday) | none | 23★, 2020. Would need to download+unzip to confirm STEP. Mark **unverified**. |
| [xiaochutan123l/MyRobotArm-stepperMotor](https://github.com/xiaochutan123l/MyRobotArm-stepperMotor) | new | **NO** | n/a | YES (closed-loop stepper) | GPL-3.0 | Stepper but no STEP CAD. |
| [NuwanJ/robot-arm-stepper](https://github.com/NuwanJ/robot-arm-stepper) | new | **NO** | n/a | YES (stepper) | GPL-3.0 | No STEP. |
| [EARodriguezM/E6R-1](https://github.com/EARodriguezM/E6R-1) | new | **NO** | 6-DOF | unconfirmed | none | "Comprehensive open-source manipulator" but no STEP in tree. |
| [SaikiranGopal3009/robot-converter](https://github.com/SaikiranGopal3009/robot-converter) | new | yes (1 test `.step`) but **NOT AN ARM** | — | — | none | STEP→URDF converter tool; `test_data/industrial_arm.step` is sample data only. Exclude. |

### Already-cloned arms re-surfaced by my searches (confirming coverage, NOT new)
`SkyentificGit/SmallRobotArm` (has `Fusion360/*.step`), `surynek/RR1`,
`Martin-Ansteensen/steppper-robot-arm`, `Chris-Annin/AR2`, `BCN3D/BCN3D-Moveo`,
`AngelLM/Thor`, `fabien-prog/6AR-...`. All in the prior set.

### List-mining result (READMEs read as full text, not just URL-regex)
I read the full text of both curated lists. Findings beyond the URL extraction:
- `hobofan/collected-robotic-arms` arms NOT already cloned and NOT BetaBots are all
  either commercial-closed (DOBOT M1/Magician, 7Bot, uArm Swift/Pro, Niryo One — no open
  hardware files), or open but **STL-only / non-stepper**: Lite Arm i2 (STL), ancastrog
  6-DOF (STL), jjshortcut 7-servo (servo, STL), Idegraaf SCARA (STL), Bender
  (`OpenArmFramework/bender_description` — files "Unknown", confirmed 0 STEP in tree
  above). **None add a NEW stepper+STEP arm.** The list lists **Thor and BetaBots** as the
  only "STEP,STL" entries — Thor is already cloned, BetaBots is my one new find.
- `adafruit/awesome-open-source-robotic-arms` (Hardware section): AR4-MK3 (already
  cloned), Arctos (already cloned), OpenExo (exoskeleton, not an arm), Pedro (servo,
  flagged above), Reachy 2 (humanoid SDK, not a printable stepper arm), HowToMechatronics
  SCARA (servo/guide). **No NEW stepper+STEP arm.**
So list-mining adds **zero** further NEW in-scope arms — but this is now evidence-backed
(full-text read), not an artifact of the URL regex.

## Bottom line
After list-mining + repo/code search + tree-level verification, the only **NEW,
genuinely-stepper** arm that ships **real loose STEP** is **`4ndreas/BetaBots-Robot-Arm-Project`**
(9 `.stp`, GPL-3.0, NEMA17/23, 386★). Every other STEP-rich arm I found is a **servo**
arm (Manuel-1.0, Jeffh1505, charm, reBot-DevArm, Pedro) — out of scope but flagged. The
NEW stepper arms (Aegis-V, thnsmmrs cycloidal, xiaochutan, NuwanJ) do **not** ship STEP;
`gouldpa/Triple-Cycloidal` is **unverified** (STEP may be zipped). `gh search code
--extension step` is an unreliable discovery channel (STEP blobs aren't text-indexed —
extension+keyword combos returned empty), so its emptiness is not evidence of absence;
the tree-grep verifier is what produced every confirmed result here.
