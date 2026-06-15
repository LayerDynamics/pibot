# Open-Source Stepper Robot Arms on GitHub — Which One Fits PiBot

## Executive summary

There is a healthy field of open-source **stepper-driven** 6-DOF (and one 5-DOF) robot arms on GitHub — the credible contenders are **AR4/AR3/AR2** (Annin), **Thor**, **BCN3D Moveo**, **Arctos**, **Faze4/PAROL6** (Source Robotics), **Dummy-Robot**, **SmallRobotArm**, and a long tail of smaller repos. For PiBot — a Pi 5 brain driving a Creality 4.2.2 (STM32F103, 4 onboard step/dir drivers, 24 V), custom AccelStepper/ASCII+CRC firmware, an `ArmManager` plus a swappable kinematics solver seam, and a ROS2 bridge — the best fit is **BCN3D Moveo for the mechanics + its MIT `moveo_ros` URDF for the solver seam**, with **AR4 as runner-up** (lift its MIT URDF only, or let it bring its own controller). The single most important constraint dominates every option: **every credible 5–6 DOF stepper arm needs ~6 drivers and the 4.2.2 has only 4, so a second board / driver expansion is mandatory no matter which arm you pick.** Two task-given rules break the tie between the agents' three different "winners": **controller-fit is the binding axis** (so AR4, which mandates a Teensy 4.1 + encoders, is disqualified *as a 4.2.2 host* and survives only as a kinematics donor), and **the wire protocol is explicitly *not* a discriminator** (PiBot flashes its own firmware and reuses geometry — which dissolves AR2's only advantage, and AR2 ships no separable URDF). The arm that wins the **intersection** of "open-loop step/dir like the 4.2.2" **and** "permissive, separable kinematics" is Moveo.

## The key constraint, stated plainly

**A Creality 4.2.2 has 4 onboard stepper drivers (X/Y/Z/E). Every credible 5–6 DOF stepper arm needs 5–7 drivers.** Therefore a 5–6 DOF build on the 4.2.2 **requires a second board (4 + 4 = 8 channels), a higher-socket board, or external driver modules off spare GPIO** — regardless of which arm's mechanics you copy. None of these arms "drop in" to a single bare 4.2.2.

Two corollaries:

- **CPU is a red herring.** PiBot runs IK host-side on the Pi; the 4.2.2 only receives per-joint targets and emits step/dir. The F103's lack of FPU / 72 MHz clock does not bite, because the MCU never does kinematics. grblHAL on an F103 sustains ~150 kHz/axis at 6 axes — far above any joint's step rate.
- **Motor current does bite.** Onboard A4988/TMC2208-class drivers source ~1.2–2 A — fine for **NEMA 17**, **not** for the **NEMA 23 (~3 A)** base/shoulder joints on Moveo and Arctos. Those joints need **external TB6600/DM542** drivers fed step/dir from GPIO (still compatible, just not "onboard").

## Master comparison table (genuinely STEPPER arms)

Servo arms (the entire EEZYbotARM family) are flagged and excluded — see the capsule below. Star counts are approximate API snapshots (2026-06-15) and drift daily.

| Arm | Repo (URL) | DOF | Steppers / gearing | Controller & firmware | 4.2.2 controller-compat | Kinematics / ROS reuse | ~BOM cost | Maturity (stars / active?) | License |
|---|---|---|---|---|---|---|---|---|---|
| **BCN3D Moveo** | [BCN3D/BCN3D-Moveo](https://github.com/BCN3D/BCN3D-Moveo) · [jesseweisberg/moveo_ros](https://github.com/jesseweisberg/moveo_ros) | 5 | NEMA 23 + 17 (+ servo gripper); belt / low-reduction | Mega + RAMPS 1.4, Marlin (G-code); ROS path uses rosserial joint-angles | **Adaptable** | **High** — MIT URDF + joint-angle Arduino driver is ArmManager's twin | ~$400 | ~1.9k★ hardware repo; `moveo_ros` 324★ MIT; dormant upstream | MIT |
| **Annin AR4 (MK3/MK4)** | [Annin-Robotics/ar4-hmi](https://github.com/Annin-Robotics/ar4-hmi) · [ycheng517/ar4_ros_driver](https://github.com/ycheng517/ar4_ros_driver) | 6 | NEMA 17 + 23, integrated encoders; belts + planetary, machined | **Teensy 4.1** + Arduino Nano; custom ASCII-degrees serial; ROS2 driver | **Hard** (needs its own controller) | **High** — MIT xacro URDF + best-in-class ROS2/MoveIt2 | ~$1.8k–3k; electronics ~$617 | driver 150★ MIT, **active (2026)** | hmi NOASSERTION; ROS2 driver MIT |
| **Annin AR3** | [ongdexter/ar3_core](https://github.com/ongdexter/ar3_core) · mirror [kentavv/annin_robotics_ar3](https://github.com/kentavv/annin_robotics_ar3) | 6 | NEMA steppers + encoders; belt/geared, machined | Teensy 3.5 (motors+encoders) + Mega; custom ASCII serial | **Hard** (Teensy coprocessor) → Adaptable if stripped to open-loop | **High** — plain MIT `ar3.urdf` is the cleanest ikpy drop-in | ~$1.5k+ | core 120★ MIT; mirror ~10★ (2020) | MIT (core) |
| **Annin AR2** | [Chris-Annin/AR2](https://github.com/Chris-Annin/AR2) | 6 | 6× stepper → external DM-series drivers; belt/geared | **Arduino Mega**, open-loop; custom **ASCII serial** | **Adaptable** (friendliest electrically) | **Low** — no separable URDF/ROS; use AR3 geometry | ~$1.5k class | ~1.45k★, stale (2019) | none declared |
| **Thor** | [AngelLM/Thor](https://github.com/AngelLM/Thor) · [AngelLM/Thor-ROS](https://github.com/AngelLM/Thor-ROS) | 6 | NEMA17-class, ~7 A4988 (dual-motor joints); printed gears + GT2 | Mega + custom RAMPS-shield, **modified GRBL (G-code)** | **Adaptable** (7 drivers ⇒ 2nd board) | **Medium** — full ROS2/MoveIt2 URDF but **copyleft** | <€350 (~$380) | ~1.5k★, light activity (2025) | CC-BY-SA-4.0 (+ GPL-3.0 URDF fork) |
| **Arctos** | [Arctos-Robotics/ROS](https://github.com/Arctos-Robotics/ROS) · [cr0Kz/ros2_arctos](https://github.com/cr0Kz/ros2_arctos) | 6 | NEMA 17 + 23; belts + **cycloidal** | Open-loop: Mega + CNC shield, mod GRBL. Recommended: **MKS closed-loop over CAN** | **Adaptable** (open-loop) / **Hard** (closed-loop CAN) | **High (kinematics)** — Apache-2.0 ROS2 URDF | ~$326–400+ | ROS 93★; ros2_arctos 16★ Apache-2.0 (2025); **CAD is paid/closed** | MIT / Apache-2.0 (code); CAD closed |
| **Faze4** | [Source-Robotics/Faze4-Robotic-arm](https://github.com/Source-Robotics/Faze4-Robotic-arm) | 6 | 3× NEMA23, 2× NEMA17, 1× NEMA14; **printed cycloidal** | **Teensy 3.5**; custom firmware | **Hard** (Teensy + 6 drivers) | Medium | ~$1k–1.5k | ~860★, light (2025) | CERN-OHL-S-2.0 |
| **PAROL6** | [PCrnjak/PAROL6-Desktop-robot-arm](https://github.com/PCrnjak/PAROL6-Desktop-robot-arm) | 6 | 6× stepper; belt/geared | **Custom STM32F446 + 6× TMC5160** board, CAN | **Hard** (bespoke board) | Med–High (Python API + ROS2) | (kit/board) | ~2.95k★, **active (2026)** | GPL-3.0 |
| **Dummy-Robot** | [peng-zhihui/Dummy-Robot](https://github.com/peng-zhihui/Dummy-Robot) | 6 | **closed-loop steppers over CAN**; harmonic/cycloidal | Custom STM32F4 + ESP32 + per-motor Ctrl-Step (CAN) | **Hard** (custom CAN/FOC) | **Low** — no URDF, IK welded into firmware, no license | high (machined) | ~15.1k★, semi-dormant (2024) | none declared |
| **SmallRobotArm** | [SkyentificGit/SmallRobotArm](https://github.com/SkyentificGit/SmallRobotArm) | 6 | 6× stepper; ~0.1 mm precision | Arduino-class MCU | Adaptable (open-loop) | Low–Med (no clean URDF pkg) | (DIY) | ~1.46k★, stale (2019) | GPL-3.0 |
| **WLkata Mirobot** | [wlkata/mirobot-py](https://github.com/wlkata/mirobot-py) · [kimsooyoung/mirobot_ros2](https://github.com/kimsooyoung/mirobot_ros2) | 6 | integrated steppers; geared | **Closed commercial** controller, GRBL-derived (G-code) | **Hard / N/A** (sealed board) | Low–Med (community URDF only) | product (not a BOM) | SDK ~12–19★ | firmware closed; SDK/URDF MIT |
| **EEZYbotARM** (mk1/2/3) | [meisben/easyEEZYbotARM](https://github.com/meisben/easyEEZYbotARM) | 3–4 | **SERVO** (mk3 has tiny steppers) | Arduino + servo PWM | **N/A — wrong actuator class** | Med (MIT Python IK is a *reference*, not geometry) | ~$25–80 | ~100★ | MIT |

## Per-arm capsules

**BCN3D Moveo — the recommended fit.** A 5-DOF, fully 3D-printable arm, ~$400 BOM, **MIT** — the cheapest credible stepper arm with a clean, separable kinematics package. It is *open-loop step/dir*, which is exactly the 4.2.2's control model. Its [jesseweisberg/moveo_ros](https://github.com/jesseweisberg/moveo_ros) (MIT, 324★) ships a `moveo_urdf` package and — crucially — a **rosserial Arduino driver that consumes per-joint angles and emits steps**, which is the literal conceptual twin of PiBot's `ArmManager`. The catch: only **5 DOF** (PiBot wants 5–6, so this is the low end), its heavy joint uses a **NEMA 23 needing an external driver**, real payload is ~100–300 g (ignore the "2 kg" claim), and upstream is dormant.

**Annin AR4 — the runner-up / best engineering.** True 6-DOF, ~1 kg+ payload, machined-quality, and **the strongest software story** — [ycheng517/ar4_ros_driver](https://github.com/ycheng517/ar4_ros_driver) (MIT, 150★, active 2026) is full ros2_control + MoveIt2, with an MIT xacro URDF and an ASCII-degrees serial protocol that is already nearly PiBot-shaped. The catch for the 4.2.2: it **mandates a Teensy 4.1 + per-joint encoders (closed-loop homing)**, so it does **not** host on a 4.2.2. For PiBot, AR4's value is its **MIT URDF** (harvest it for the solver seam) — or you let AR4 keep its own Teensy controller and use PiBot only as the ROS2/host brain. Higher cost (~$1.8k+) and a machined-heavy build.

**Annin AR3 — best *cleanest* kinematics donor.** [ongdexter/ar3_core](https://github.com/ongdexter/ar3_core) (MIT, 120★) ships a **plain non-xacro `ar3.urdf`** — the single easiest artifact to load with `ikpy.chain.Chain.from_urdf_file()` in one line. As hardware it's "Hard" (Teensy 3.5 encoder coprocessor); stripped to open-loop it collapses into AR2. Best treated as a **geometry/URDF donor**, not a controller target.

**Annin AR2 — friendliest electronics, weakest software.** The one Annin arm that is **already open-loop step/dir + custom ASCII serial on an Arduino Mega** — electrically the closest of the named set to PiBot's firmware model (Agent 2 called it the "single best fit"). But the task makes **protocol match a non-discriminator** (PiBot flashes its own firmware), which dissolves that advantage, and AR2 has **no separable URDF/ROS** of reuse value — it is superseded by AR3's MIT geometry. Use AR3's `ar3.urdf` for the seam and AR2 only for build reference.

**Thor — iconic, cheap, copyleft.** Fully printed 6-DOF, <€350, ~625 mm reach, ~750 g payload, huge community. Step/dir A4988 with **~7 drivers** (dual-motor joints) ⇒ needs a 2nd 4.2.2; no closed-loop, so electrically the friendliest of the "needs 2 boards" arms. Full **ROS2 Humble + MoveIt2** URDF exists — but every kinematics artifact is **copyleft (CC-BY-SA-4.0 / GPL-3.0)**. For PiBot, **re-derive DH from the geometry** (DH numbers aren't copyrightable) rather than vendoring the URDF. Printed-gear backlash is worse than cycloidal.

**BCN3D Moveo vs. Arctos.** Arctos is a capable printed 6-DOF with **cycloidal** gearboxes, ~600 mm reach, and a permissive **Apache-2.0 ROS2 URDF** ([cr0Kz/ros2_arctos](https://github.com/cr0Kz/ros2_arctos)) that's directly seam-usable. Two catches: its **recommended build is closed-loop MKS steppers over CAN** (a different controller class — "Hard"; only the open-loop Mega+CNC-shield variant is "Adaptable"), and its **CAD is sold (€39.95), not open** — a real problem for a fully-open PiBot.

**Faze4 / PAROL6 (Source Robotics).** Faze4 is the **best fully-printable 6-DOF mechanics** — low-backlash printed cycloidals, the nicest drivetrain for a clean IK story — but it's a ~1000-part advanced build on a **Teensy 3.5**, and PAROL6 (its successor) runs a **bespoke STM32F446 + 6× TMC5160 board** that already *is* a purpose-built arm controller. Both are "Hard" for a 4.2.2; PAROL6 is the reference for "what a dedicated STM32 arm board looks like." Strong mechanics donors, not 4.2.2 hosts.

**Dummy-Robot — impressive, unusable for reuse.** The most-starred (~15k) 6-axis arm, but **closed-loop steppers over CAN on a bespoke distributed STM32/FOC architecture**, CNC-machined, Chinese-only docs, **no license** (all-rights-reserved), and IK welded into firmware. Nothing maps onto a 4.2.2 and nothing is legally reusable. Expert-only.

**Mirobot — a product, not a build.** A finished commercial educational arm with open-ish (GRBL-derived, G-code) firmware on a **sealed controller** you can't reflash. Only community Python SDK + ROS2 URDF are open. Out of PiBot's "flash our own board" model.

**EEZYbotARM — why it keeps appearing, why it's excluded.** It dominates "open-source robot arm" searches and is constantly mistaken for a stepper arm, but the mk1/mk2 are **hobby-servo** driven (mk3 swaps in tiny, "weak" steppers at 3–4 DOF, ~tens of g payload). Wrong actuator class for a stepper board and off-spec on DOF. Its one lasting value is `kinematic_model.py` (MIT) — the **best Python analytic-IK reference to model PiBot's `IKSolver` on** (copy the *pattern*, not the geometry).

## Compatibility deep-dive for PiBot

### (a) Controller — Direct / Adaptable / Hard on a 4.2.2

- **Direct:** none. No 5–6 DOF arm fits one bare 4.2.2 (4-driver ceiling). A sub-4-DOF NEMA17 step/dir arm would be Direct, but that's below PiBot's 5–6 DOF target.
- **Adaptable** (step/dir model matches; needs a 2nd board and/or external drivers): **AR2** (open-loop, external drivers already — friendliest), **Thor** (~7 A4988 ⇒ 4+4), **BCN3D Moveo** (5 drivers + NEMA23 external driver), **open-loop Arctos**, **SmallRobotArm**. These are the arms whose control model (per-joint step/dir, endstop homing, soft limits, e-stop) *is* PiBot's firmware model.
- **Hard** (mandates a different controller class — won't host on a 4.2.2 with AccelStepper firmware): **AR4** (Teensy 4.1 + encoders), **AR3** (Teensy 3.5 encoder coprocessor), **Faze4** (Teensy 3.5), **PAROL6** (bespoke STM32F446 + TMC5160), **Dummy-Robot** and **closed-loop Arctos** (MKS/custom closed-loop CAN servos), **Mirobot** (sealed commercial board).

**The 4-driver / 2nd-board reality:** plan a **second 4.2.2** (4 + 4 = 8 channels) for drivers 5–6 (and 7 for Thor's dual-motor joint). **NEMA 23 joints** (Moveo base/shoulder, Arctos X/Y) exceed the onboard ~2 A ceiling and need **external TB6600/DM542 drivers** fed step/dir from GPIO. Avoid the **closed-loop/CAN** arms (Dummy, closed-loop Arctos, Mirobot) entirely on this axis — they have no central step/dir board for the 4.2.2 to replace.

### (b) Software — reusable kinematics for the solver seam + ROS2

PiBot's seam is a `JointSolver` Protocol (`solve(target) -> {joint_id: degrees}`); an `IKSolver` drops in once link geometry/DH/URDF is known, with no firmware or `ArmManager` change. Ranked by "separable, permissively-licensed URDF/DH that feeds an ikpy/MoveIt solver":

1. **AR3 `ar3.urdf` (MIT)** — plain URDF, one-line ikpy load. Cleanest drop-in.
2. **AR4 `annin_ar4_description` (MIT)** — xacro (one expansion step), most maintained, full ROS2/MoveIt2.
3. **Moveo `moveo_urdf` (MIT)** — cleanest **5-DOF**, and its joint-angle Arduino driver is the conceptual twin of `ArmManager`.
4. **Arctos `arctos_description` (Apache-2.0)** — permissive ROS2 URDF; use if going the ROS2-bridge route.
5. **EEZYbotARM `kinematic_model.py` (MIT)** — not geometry, but the Python-IK *structure* to mirror.
6. **Thor (CC-BY-SA-4.0 / GPL-3.0)** — technically full ROS2/MoveIt2, but copyleft → re-derive DH instead of vendoring.

**Best ROS2 + MoveIt2** (maps to PiBot's `pibot/ros2/` bridge): **AR4** (MIT, strongest, active) > **Arctos** (Apache-2.0) > **Thor** (copyleft). AR3 core is ROS1 (ROS2 config exists but is unlicensed); Moveo/Mirobot are primarily ROS1.

**The wire protocol is a non-blocker.** PiBot flashes its own firmware and keeps its ASCII+CRC link; it reuses each arm's **geometry**, not its G-code/rosserial/ASCII wire format. So a Marlin/GRBL/G-code firmware on the donor arm does **not** lower its score — only entanglement of the *kinematics* with that firmware does (which is why Dummy-Robot, with IK welded into firmware, scores Low). This is the rule that decouples "whose mechanics" from "whose URDF."

**Watch copyleft on URDFs.** A URDF *file* is copyrightable: AR3/AR4/Moveo = MIT, Arctos = Apache-2.0 (all clean to vendor); Thor = CC-BY-SA/GPL (re-derive DH); Dummy-Robot = no license (unusable). DH *numbers* are not copyrightable, so re-deriving DH from an inspectable URDF sidesteps a copyleft file. URDF/ikpy/MoveIt work in **radians**; the seam wants **degrees per logical joint id**, so every path needs a small rad→deg + joint-reorder shim.

## Viability ranking (best → worst for a Pi-driven 5–6 DOF hobby build)

1. **BCN3D Moveo** — cheapest credible 5-DOF (~$400), MIT, fully printable, kinematics already lift into the seam. Accept ~100–300 g payload and a 2nd driver board.
2. **Annin AR4** — best engineering, true 6-DOF, ~1 kg+ payload, active ROS2/MoveIt2 — but pricier (~$1.8k+), machined-heavy, and needs its own Teensy controller (not the 4.2.2).
3. **Faze4** — best fully-printable 6-DOF mechanics (low-backlash printed cycloidals), but ~1000-part advanced build on a Teensy.
4. **Thor** — iconic, cheap (<$380), great community, but printed-gear backlash and copyleft kinematics.
5. **Arctos** — capable 6-DOF cycloidal with a big builder base, but **CAD is paid/closed** and the recommended build is closed-loop CAN.
6. **AR3 / AR2** — legacy; harvest AR3's MIT URDF, otherwise build the AR4 instead.
7. **EEZYbotARM (mk3/2/1)** — wrong scale (3–4 DOF, tiny payload, mostly servo); learning warm-up only.
8. **Dummy-Robot** — expert-only (CNC + custom-PCB + closed-loop CAN, Chinese docs, no license).
9. **WLkata Mirobot** — a finished commercial product, not a from-BOM build.

## Recommendation for PiBot

**Primary pick: BCN3D Moveo (mechanics) + `jesseweisberg/moveo_ros` MIT URDF (solver seam).** It is the only contender that wins the **intersection** of PiBot's two hard requirements: it is **open-loop step/dir** (so it matches the 4.2.2's firmware model — "Adaptable," not "Hard"), and it donates **permissive, separable kinematics** (MIT URDF + a joint-angle Arduino driver that is the conceptual twin of `ArmManager`). It is also the cheapest credible build (~$400) and fully printable.

Concrete path:

- **Kinematics:** load `moveo_urdf` into `ikpy` (`Chain.from_urdf_file`), wrap with a rad→deg + joint-reorder shim, and expose it as a PiBot `IKSolver` satisfying `solve(pose) -> {joint_id: degrees}`. No firmware or `ArmManager` change. (If you later want 6 DOF, swap in **AR3's plain MIT `ar3.urdf`** — same seam, one-line load.)
- **Drivers:** add a **2nd 4.2.2** for the 5th stepper (4 + 4 = 8 channels), and feed the **NEMA 23 base/shoulder joint from an external TB6600/DM542** driver via GPIO (onboard ~2 A can't source ~3 A).
- **Firmware:** keep PiBot's AccelStepper/ASCII+CRC firmware and flash both 4.2.2 boards; drive steps from a hardware-timer ISR (as grblHAL/Marlin do) rather than leaning on `AccelStepper::run()` polling, for smooth multi-axis ramps. The protocol shim is trivial — you reuse Moveo's geometry, not its rosserial/G-code link.

**Runner-up: Annin AR4.** Pick AR4 if you want true 6-DOF, ~1 kg+ payload, and the strongest active ROS2/MoveIt2 stack, and are willing to either **(a) harvest only its MIT xacro URDF** into the solver seam while building Moveo-class step/dir electronics, or **(b) let AR4 keep its own Teensy 4.1 controller** and use PiBot as the host/ROS2 brain. The trade-off is honest: AR4 is the better robot but is **"Hard" on the 4.2.2 axis** (Teensy + encoders) and ~4–7× the cost — so it loses the *primary* slot precisely because the 4.2.2 is PiBot's binding constraint.

**For a 6-DOF, fully-open, 4.2.2-centric build**, the pragmatic blend is **Moveo/Thor-class open-loop step/dir mechanics + AR3's MIT URDF geometry** (or re-derived DH for Thor) — keeping every layer permissive and on PiBot's existing stack.

## Caveats / confidence

- **Costs, payloads, reach, and star counts are approximate** — pulled from READMEs, vendor pages, and build logs, and they drift by build, currency, and date. Treat printed-arm payloads especially loosely: vendor "2 kg" claims (Moveo, Arctos) are marketing; realistic safe payload at hobby driver currents is **~100–500 g**.
- **AR3's serial protocol was not source-verified** (only AR4's `teensy_driver.cpp` was read); it's *inferred* Annin lineage. Non-blocking — kinematics reuse is protocol-independent.
- **Star counts that look like conflicts across agents are different repos, not contradictions** — e.g. `kentavv/annin_robotics_ar3` (mirror, ~10★) vs `ongdexter/ar3_core` (120★), and `BCN3D/BCN3D-Moveo` (~1.9k★ hardware) vs `jesseweisberg/moveo_ros` (324★ software). Both rows in each pair are kept.
- **Thor's ~7-driver count** is inferred from its 8-socket ControlPCB + 6-DOF dual-motor layout (the electronics doc was unreachable at fetch time).
- Single-sourced where noted: Thor driver count, Mirobot/Dummy internals (closed/Chinese-docs), and the smallest long-tail repos' DOF/motor facts (READMEs only).

---

Sources: see [Sources.md](./Sources.md) for the deduped master URL list grouped by project/topic.
