# Agent 4 Findings — Viability of Open-Source Stepper Robot Arms (for PiBot)

**Facet:** Mechanical design, BOM/cost, DOF/payload/reach, gearing, build difficulty, and
project maturity/community.

**Lens (PiBot):** A Raspberry-Pi-5 "brain" driving a Creality 4.2.2 board (STM32F103,
**4 stepper drivers**, 24 V), targeting a **5–6 DOF hobby/maker-scale arm**. Favor arms that
are buildable, affordable, well-documented, 5–6 DOF, and have realistic (low) payload
expectations for printed structures.

> All figures are **approximate** — costs, GitHub stars, and payloads vary by build,
> currency, and date. Numbers were pulled from project READMEs, vendor pages, build logs,
> and forum threads (see `Agent4Sources.md`). Stepper-driver count and 24 V/NEMA fit are
> the controller-axis constraints carried from `ExpandedSearches.md`; here they inform the
> viability verdict, not the primary scoring.

---

## Per-project viability table

| Project | DOF | Reach (approx) | Payload (approx) | Steppers | Gearing / transmission | Closed-loop needed? | Construction | BOM cost (USD, approx) | Build difficulty | Maturity (stars / activity / license) | Viability verdict (Pi-driven 5–6 DOF hobby) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Annin AR4** (MK3/MK4) | 6 | ~600–630 mm | ~1–1.9 kg | NEMA 17 + NEMA 23, 6 motors, **with integrated encoders** | Belts + planetary/geared joints; precision-machined joints | Encoders standard (closed-loop), not strictly required to move | Printed + **machined aluminum** option; metal kit available | ~$1,800–3,000 full; electronics pkg ~$617 | Advanced | Driver `ar4_ros_driver` ~150★, MIT, **active (ROS2 Jazzy, late 2024)**; maintained by Chris Annin; **excellent manuals + video**; large community, paid kits | **Best-engineered; best if budget allows.** Mature, 6-DOF, real payload, ROS2/MoveIt2 ready — but pricier and machined-heavy, so it ranks #2 for this cheap-hobby use case. Uses Teensy 4.1 + 6 drivers — **does NOT fit a 4.2.2** (needs its own controller / 2nd board). |
| **Faze4** (PCrnjak) | 6 | ~tabletop (mid) | low (printed, ~hundreds of g) | 3× NEMA 23, 2× NEMA 17, 1× NEMA 14 (6 motors) | **3D-printed cycloidal gearboxes** (J1–J5) + belts; planetary on J6 | No (open-loop steppers) | **Fully 3D-printable** (~1000 parts, ~15 kg arm) | ~$1,000–1,500 | Advanced (≈1000 parts) | Hackaday-featured; **ReadTheDocs build docs**; source-robotics blog + community; active; open-source design | Strong 6-DOF printable design with **low-backlash cycloidals** (great for a Pi solver). Needs 6 drivers → 2nd board beyond a 4.2.2. Build is long but well-documented. |
| **BCN3D Moveo** | 5 | ~mid (no official mm; ~0.45–0.5 m class) | ~0.1–2 kg (design target 2 kg; real-world ~100 g on NEMA17 at safe current) | NEMA 17 / NEMA 14 / NEMA 23 (5 motors) + servo gripper | **Direct + belt/geared**, mostly low-reduction → noticeable backlash | No | **Fully 3D-printable** | ~$400 | Intermediate | **~1.9k★**, MIT, **few commits / dormant** upstream; **EN/ES manuals**; very large fork ecosystem (Marlin + `moveo_ros` w/ MoveIt + URDF) | **Most viable cheap printable 5-DOF.** Cheapest credible 5-DOF, MIT, ROS/URDF forks exist. Payload is optimistic — treat as ~100–300 g. Uses RAMPS/Mega + 5 drivers (not a 4.2.2). |
| **Thor** (AngelLM) | 6 | ~625 mm tall extended | ~750 g | Steppers (NEMA17-class), gear+belt drive | **3D-printed gears + GT2 belts/pulleys** | No | **Fully 3D-printable** | <€350 (~$380) | Advanced | **~1.5k★**, CC BY-SA 4.0, last tagged v2.1 (Sep 2021), Discord + forum, ~30+ builds in 17 countries; slow upstream | Iconic, cheap, 6-DOF, great docs/community. Printed-gear drivetrain → more backlash/wear than cycloidal. GRBL firmware (G-code) + custom PCB; needs its own driver board. |
| **Arctos** | 6 | ~600 mm | ~2 kg (vendor claim; optimistic for printed) | NEMA 17 + NEMA 23 (6) | Belt drives + **cycloidal gearboxes** | Newer "Closed Loop" version exists; open-loop version also sold | **Fully 3D-printable** (~3 kg filament) | ~$326–400+ kit; CAD files **€39.95 (sold, not open)** | Intermediate–Advanced | GRBL firmware **open** (~67★) + ROS/MoveIt GUI repos; **CAD is paid/closed**; large builder base ("4,000+ built"); active 2024–2025 | Good 6-DOF printable w/ cycloidals and a big community, **but the CAD is not open-source** (paid). Arduino Mega + CNC shield + 6 drivers — not a 4.2.2 fit. License caveat matters for a fully-open PiBot. |
| **Annin AR3 / AR2** | 6 | ~600 mm | ~1 kg | NEMA steppers (6) | Belt + geared joints; machined | No (AR3/AR2 open-loop; AR4 added encoders) | Printed + machined aluminum | ~$1,500+ (AR2/AR3 kit class) | Advanced | Superseded by AR4; older community; open source | Legacy — **just build the AR4 instead.** AR4 is the maintained successor with ROS2 support. |
| **EEZYbotARM MK1** | 4 | tiny (desk-toy) | ~5 g (a marble) | **None — micro servos** (MG90S) | Linkage | n/a | Fully 3D-printable | ~$25–40 | Beginner | Very popular original; free STLs; `easyEEZYbotARM` Python IK (Mk1/Mk2); CC license; large maker following | Pure learning toy — **servo-driven, 4 DOF, ~5 g payload.** Way under-spec for the target; only useful as a kinematics warm-up. |
| **EEZYbotARM MK2** | 4 | small (~ desk-toy) | ~tens of g (MG-class servos) | **None — hobby servos** (MG946R + SG90) | Linkage (ABB IRB460 1:7 scaled) | n/a | Fully 3D-printable | ~$30–60 | Beginner | Hugely popular on Thingiverse; `easyEEZYbotARM` Python lib (IK for Mk1/Mk2); good step-by-step Instructables; CC license | Great learning toy but **servo-driven and only 4 DOF** — off-spec for a 5–6 DOF stepper arm. |
| **EEZYbotARM MK3** | 3–4 | small | low (steppers found "weak") | Small bipolar steppers (e.g., 28BYJ-class / small NEMA) | Linkage + reworked vertical-arm transmission | No | Fully 3D-printable | ~$40–80 | Beginner–Intermediate | Free STLs (Thingiverse/Cults3D); smaller community than Mk2 | The "stepper EEZYbot," but **3–4 DOF and tiny payload.** Good 4.2.2 driver-count fit, wrong DOF/scale for the target. |
| **Dummy-Robot** (peng-zhihui) | 6 | small/desktop | low | 20/42/57-size steppers w/ **closed-loop + CAN** | Custom; "Youth" version uses 3D-printed **cycloidal** reducer | **Yes — closed-loop CAN steppers** | Original **CNC-machined**; "Youth" 3D-print version planned/partial | high (machined, custom PCBs) | Advanced/Expert | **~15k★** (most-starred), STM32 firmware, docs **in Chinese**, last major activity ~2022 | Impressive but **expert-only**: CNC/custom-PCB/closed-loop-CAN, Chinese docs, semi-dormant. **Not a fit** for a 4.2.2 / step-dir hobby build. |
| **WLkata Mirobot** | 6 (+1) | small desktop | ~150 g | Steppers (6) | Geared; precision | No | **Commercial product** (sells assembled kit) | Product, not a DIY BOM (~kit price) | n/a (buy, not build) | Open API/firmware (Arduino/GRBL-based); good vendor docs | **Not a DIY arm** — it's a finished educational product with open firmware. Out of scope for a from-BOM hobby build. |

---

## Notes that change the verdict

- **Payload realism:** Printed arms (Moveo, Thor, Faze4) are **low-payload**. Treat vendor
  "2 kg" claims (Moveo, Arctos) as marketing; real safe payload for a printed 5–6 DOF arm at
  hobby driver currents is roughly **100–500 g**. AR4 is the only one here with a credible
  ~1 kg+ payload, and it pays for that with machined parts and a higher BOM.
- **Gearing quality ladder (best → worst for a Pi solver):** cycloidal (Faze4, Arctos,
  Dummy "Youth") > planetary > belt > **printed spur gears** (Thor) ≈ low-reduction direct
  (Moveo). Lower backlash = a cleaner story for PiBot's IK/JointSolver seam.
- **Controller-axis reality (carried constraint):** **Every credible 5–6 DOF arm needs 6
  stepper drivers**, but a Creality 4.2.2 has only **4**. So a 5–6 DOF build on the 4.2.2
  requires a **second board or a driver-expansion** regardless of which arm's mechanics you
  copy. None of these arms "drop in" to a single 4.2.2.
- **License caveat:** Arctos sells its CAD (not open); Dummy docs are Chinese-only. AR4,
  Moveo (MIT), Thor (CC BY-SA), and Faze4 are the cleanly-open mechanical designs.

---

## Ranked shortlist — best → worst for a **Pi-driven 5–6 DOF hobby build**

1. **BCN3D Moveo** — *Best value entry point.* Cheapest credible 5-DOF (~$400), **MIT**,
   fully printable, and the fork ecosystem already has Marlin firmware + `moveo_ros`
   (MoveIt + URDF) to lift into PiBot's solver seam. Accept ~100–300 g real payload and
   plan a 2nd driver board.
2. **Annin AR4** — *Best engineering & support, if budget/effort allow.* True 6-DOF,
   ~1 kg+ payload, repeatable, **actively maintained ROS2/MoveIt2 driver**. Costs more
   (~$1.8k+) and is machined-heavy; needs its own Teensy-class controller (not the 4.2.2).
3. **Faze4** — *Best fully-printable 6-DOF mechanics.* Open design with **low-backlash
   3D-printed cycloidals** — the nicest drivetrain for a clean IK story. ~$1–1.5k and a
   ~1000-part advanced build; 6 drivers needed.
4. **Thor** — *Iconic, cheap, well-documented 6-DOF.* <$380 and a strong community, but
   printed-gear backlash/wear and GRBL/G-code firmware on a custom PCB make it a
   middling fit for a precise Pi solver.
5. **Arctos** — *Capable 6-DOF with cycloidals and a big builder base,* but the **CAD is
   paid/closed** and it's Mega+CNC-shield/6-driver based — a poor match for a fully-open,
   4.2.2-centric PiBot.
6. **AR3 / AR2** — *Legacy;* build the AR4 instead.
7. **EEZYbotARM MK3 / MK2 / MK1** — *Wrong scale:* 3–4 DOF, tiny payload (MK1 ~5 g,
   servo-driven). Fine as a learning warm-up, off-spec as the target arm.
8. **Dummy-Robot** — *Expert-only:* CNC/custom-PCB/closed-loop-CAN, Chinese docs,
   semi-dormant. Not a hobby-fit.
9. **WLkata Mirobot** — *Not a DIY build:* it's a finished commercial product (open firmware).

**Top 3 for PiBot:** **Moveo** (cheap/open/printable 5-DOF), **AR4** (mature 6-DOF with
real payload + ROS2), **Faze4** (best printable 6-DOF cycloidal mechanics).
