# Agent 3 Findings — Software / Control Stack, ROS Support & Kinematics/IK Reusability

**Facet:** Software stack, ROS2/MoveIt support, and kinematics/IK (URDF/DH) reusability for each
open-source stepper robot arm — viability of integrating with **PiBot's Python host stack**.

**Date:** 2026-06-15 · **Method:** primary-source verification via `gh api` file-tree + license
inspection of the canonical repos, supplemented by WebSearch/WebFetch for control-stack confirmation.
Every ROS/MoveIt/URDF claim below was confirmed against the actual repo tree (paths cited in
`Agent3Sources.md`), not from blog assertions.

---

## The integration target (what actually "drops in")

PiBot's solver seam is a `JointSolver` Protocol (`pibot/arm/kinematics.py`):

```python
class JointSolver(Protocol[_Intent]):
    def solve(self, target: _Intent) -> dict[int, float]: ...   # logical joint id -> DEGREES
```

Shipped today: `DirectSolver` (pass-through) and `NamedPoseSolver` (preset registry). An **IKSolver
(Cartesian pose → joint angles) drops into this exact interface once the arm's link geometry / DH /
URDF is known** — no firmware or `ArmManager` change. PiBot also has a ROS2 bridge
(`pibot/ros2/`) and speaks its **own** ASCII line+CRC serial at the firmware (NOT G-code).

**Therefore the verdict rubric (per the advisor's framing) is:**

1. **The thing that literally drops into the seam is a separable, permissively-licensed URDF or DH
   table** that can feed an `ikpy`/MoveIt solver to produce `{joint_id: degrees}`. That is the
   **"High reuse"** bar. Everything else is secondary.
2. **Do NOT double-penalize G-code / ROS-action protocols.** PiBot would flash *its own* firmware on
   the arm board and keep its ASCII+CRC link — it reuses the arm's *kinematics*, not its wire
   protocol. A Marlin/GRBL/G-code firmware only lowers the verdict **when the kinematics are
   entangled with that stack and cannot be cleanly lifted.**
3. **License is part of reusability, not a footnote.** A URDF *file* is copyrightable, so a
   GPL/CC-BY-SA URDF imposes copyleft on PiBot. **DH *numbers* are not copyrightable** — re-deriving
   DH from a published/inspectable URDF sidesteps the license. Copyleft is flagged as a reuse caveat.
4. **Units/order adapter:** URDF/MoveIt/ikpy work in **radians**; the seam wants **degrees per
   logical joint id**. "Easy to wrap" = a rad→deg + joint-reorder shim. Noted where load-bearing.

> Controller/driver-count, payload/reach/cost, and maturity are **other agents' facets** — only
> one-line pointers here.

---

## Per-project software / kinematics table

| Arm | Canonical control software (lang) | ROS / ROS2 + MoveIt | URDF? | DH / IK published | Host→board protocol | License (of the reusable kinematics) | Integration verdict for PiBot seam |
|---|---|---|---|---|---|---|---|
| **AR4** (Annin) | `Annin-Robotics/ar4-hmi` Python+C++ GUI (**NOASSERTION** license) | **YES — best-in-class ROS2 + MoveIt2** via community `ycheng517/ar4_ros_driver` (MIT, ros2_control + MoveIt2 + Servo + Pilz) | **YES** — `annin_ar4_description` xacro/URDF (mk1/mk2/mk3 + gripper) | URDF→solvable; KDL/`kinematics.yaml` present; no separate analytic DH doc needed | Firmware: **ASCII command strings, letter-tagged float degrees** over serial, `\n`-terminated, **not G-code** (verified from `teensy_driver.cpp`). *Illustrative* framing: two-letter headers (`MT` move, `JP` query) + single-letter joint tags (A,B,C…) carrying degree floats; query `JP` returns `JP<tag><deg>…`. (Exact byte literals not transcribed line-by-line; the characterization is what matters.) Very close to PiBot's ASCII line ethos. | **MIT** (the ROS2 driver/description) — clean | **HIGH.** Permissive MIT URDF + full ROS2/MoveIt2 + a serial protocol that is nearly PiBot-shaped already. Strongest overall. |
| **AR3** (Annin) | `Annin-Robotics/ar4-hmi` lineage / older AR3 Python GUI | **YES** — `ongdexter/ar3_core` (MIT, ROS1 + MoveIt); ROS2 via `RIF-Robotics/ar3_moveit2_config` (MoveIt2, **no license field**) | **YES** — `ar3_description/urdf/ar3.urdf` (+ xacro) — a **plain non-xacro `.urdf`**, easiest of all to load straight into ikpy | URDF directly | Serial to Teensy. *Protocol not independently verified for AR3* — **inferred** to be the same Annin ASCII letter-tagged degree family as AR4 (vendor lineage), not confirmed from source. Non-blocking (kinematics reuse doesn't depend on it). | **MIT** (ar3_core URDF) — clean; ROS2 config license unstated (re-derive DH to be safe) | **HIGH.** The plain `ar3.urdf` is the single cleanest drop-in for an ikpy Python solver. Slightly behind AR4 (ROS1-era core, ROS2 config unlicensed). |
| **AR2** (Annin) | Official: **Windows/Python GUI only** (`AR2.py`, ~2017 predecessor of AR3) | **No first-party ROS.** Only a tiny community catkin attempt `wesleysliao/ros-AR2-arm-workspace` (2 stars; has a `ROS_AR2_moveit_config` dir but **no `*_description`/URDF surfaced**) | **NO separable URDF found** in any Annin-owned or notable community repo | None published as a clean artifact; geometry is essentially the AR3 predecessor | Serial to Teensy/Arduino (Annin family); not independently verified | GUI: no clear OSS license; community workspace unlicensed | **LOW (standalone).** No separate URDF/ROS/MoveIt of reuse value; **superseded by AR3** — for the seam, **use AR3's MIT `ar3.urdf` geometry** rather than AR2. Listed for completeness per the task enumeration. |
| **BCN3D Moveo** | `jesseweisberg/moveo_ros` (ROS1 + Arduino), MIT | **ROS1 + MoveIt** (catkin). ROS2 forks exist (`JJJau03/moveo_RoboticArm_ROS2`) but smaller/less proven | **YES** — `moveo_urdf/` URDF + meshes; `moveo_moveit_config` with `kinematics.yaml`+SRDF | URDF + KDL; classic 5-DOF Moveo geometry widely DH-documented | **rosserial joint angles, NOT G-code** — Arduino `.ino` subscribes to `ArmJointState.msg` (per-joint step targets). Marlin-on-Moveo also exists in the wild but the canonical ROS path is joint-angle. | **MIT** | **HIGH (kinematics) / Medium (only because ROS1).** MIT URDF + the *reference* joint-angle driver pattern. The arm's own control path is already "joint angles in → steps out," exactly PiBot's model. Lift the URDF; the ROS1-ness is irrelevant since PiBot reuses kinematics, not the catkin stack. |
| **Arctos** | `Arctos-Robotics/arctosgui` (ROS1 MoveIt GUI); `Arctos-Robotics/ROS` (MIT) — **a Moveo-derived stack** (same `ArmJointState.msg`/`moveit_convert.cpp` filenames) | **YES, incl. ROS2** — community `cr0Kz/ros2_arctos` (**Apache-2.0**, ros2_control + MoveIt2, URDF on `feature/moveit_config_and_bringup`) | **YES** — `arctos_description` (ROS2, full URDF + meshes + `kinematics.yaml`) and `arctos_urdf_description` (ROS1) | URDF + KDL via MoveIt2 | **Native robot: GRBL/G-code streamed over CAN bus** (`Arctos-grbl`, `GcodeCANBus`), closed-loop steppers. But kinematics layer is separable from CAN/G-code. | **Apache-2.0** (ros2_arctos) / **MIT** (Arctos-Robotics/ROS) — clean | **HIGH (kinematics) / Medium (whole arm).** Permissive ROS2 URDF (Apache-2.0) + MoveIt2 = directly usable for the seam. The G-code-over-CAN firmware doesn't matter (PiBot flashes its own), but note Arctos uses closed-loop CAN steppers (firmware/controller facet flags this). |
| **Thor** (AngelLM) | `Asgard` — React web GUI (FK + IK), bundled in `AngelLM/Thor-ROS` | **YES — ROS2 Humble + MoveIt2** (`AngelLM/Thor-ROS`, `thor_moveit` config). Plus standalone URDF pkg `b-adkins/thor_arm_description` | **YES** — URDF in `Thor-ROS` (`thor_moveit`/description) and `thor_arm_description` | URDF + KDL; 6-DOF yaw-roll-roll-yaw-roll-yaw geometry | Firmware: **GRBL modification (G-code)** over serial | **CC-BY-SA-4.0** (Thor + Thor-ROS) and **GPL-3.0** (`thor_arm_description`) — **both copyleft** | **MEDIUM.** Full ROS2+MoveIt2+URDF exist and are technically easy to lift, BUT every kinematics artifact is copyleft (CC-BY-SA / GPL). For PiBot, **re-derive DH from the geometry** (DH numbers aren't copyrightable) rather than vendoring the URDF, or accept the copyleft obligation. Technically high reuse, legally encumbered. |
| **EEZYbotARM** (mk1/2/3) | `meisben/easyEEZYbotARM` (MIT) — pure-**Python** control lib + Arduino; `justbuchanan/eezybotarm-mk2-software` (Qt GUI) | Partial — `inaciose/eezybotarm` + `inaciose/ebamk2_description` (ROS description, small) | URDF only via small community `ebamk2_description`; **main value is the Python analytic model** | **YES — best self-contained Python IK.** `kinematic_model.py` has analytic FK/IK for mk1/mk2 + PDF derivations (`docs/kinematics/*.pdf`) | Custom Python `serial_communication.py` to Arduino (servo PWM) | **MIT** | **MEDIUM** for *this* arm (it's **RC-servo-driven, not stepper** — mismatch with the research framing; small 3-DOF + grip). **BUT its MIT analytic-IK Python module is the single best *reference implementation* to model a PiBot `IKSolver` on** — copy the pattern, not the geometry. Cite as the Python-IK exemplar. |
| **Dummy-Robot** (peng-zhihui) | Custom C++/Qt host + STM32 firmware; **Chinese docs** | ROS mentioned in IDE config only; **no usable ROS/MoveIt package** found | **NO URDF** in repo | Analytic 6-DOF IK exists but **embedded in firmware** (`2.Firmware/.../algorithms/kinematic/6dof_kinematic.cpp/.h`), entangled with the STM32 closed-loop board | Custom serial/CAN to bespoke closed-loop boards | **NO LICENSE** (all-rights-reserved) | **LOW.** No URDF, IK is welded into proprietary firmware, **no license = no legal reuse**, closed-loop custom boards. High stars (15k) but not a kinematics donor for PiBot. |
| **WLkata Mirobot** | Commercial; `wlkata-mirobot-python` / `py-mirobot` (MIT) Python SDK | Community ROS2 `kimsooyoung/mirobot_ros2` (MIT) — has `mirobot_description` URDF + meshes | **YES** (community URDF in `mirobot_ros2`) | URDF (community); analytic kinematics live in closed firmware | **G-code** firmware (GRBL-derived); SDK speaks G-code (`set_joint_angle`, `set_tool_pose`) | **MIT** (the *community* SDK/URDF only; firmware closed/commercial) | **LOW–MEDIUM.** It's a **commercial closed-firmware** product; only community wrappers are open. The community URDF is reusable, but you can't flash PiBot firmware onto a sealed commercial controller, so it's outside PiBot's "flash our own board" model. Useful only as a URDF reference. |

> **Verdict legend:** *High reuse* = separable + permissive URDF/DH, easy ikpy/MoveIt wrap. *Medium*
> = usable kinematics but legally encumbered (copyleft) or entangled with ROS/G-code. *Low* =
> closed / unlicensed / servo-only / kinematics welded into proprietary firmware.

---

## Which arms give the most reusable kinematics for PiBot's Python solver seam

Ranked by "separable + permissive URDF/DH that feeds an ikpy-style Python IK to emit
`{joint_id: degrees}`":

1. **AR3 — `ongdexter/ar3_core` (MIT).** Ships a **plain `ar3.urdf`** (not just xacro), the single
   easiest artifact to load directly into `ikpy.chain.Chain.from_urdf_file(...)`. MIT = no copyleft.
   Re-order joints + rad→deg shim and it drops into the seam. **Top pick for the Python-IK path.**
2. **AR4 — `ycheng517/ar4_ros_driver` (MIT).** `annin_ar4_description` is xacro (one
   `xacro → urdf` expansion step), but it's the most actively maintained, covers mk1/mk2/mk3, and is
   MIT. Best overall because its serial protocol is also nearly PiBot-shaped (degrees in ASCII).
3. **BCN3D Moveo — `jesseweisberg/moveo_ros` (MIT).** MIT URDF + the *canonical* "joint-angles-in →
   stepper-steps-out" Arduino reference (`ArmJointState.msg`). Conceptually the closest existing
   project to what PiBot's `ArmManager` already does. 5-DOF, ROS1, but kinematics lift cleanly.
4. **Arctos — `cr0Kz/ros2_arctos` (Apache-2.0).** Permissive ROS2 URDF + MoveIt2; good if PiBot wants
   the **ROS2 bridge path** (see below). Caveat: closed-loop CAN steppers (firmware facet).
5. **EEZYbotARM — `meisben/easyEEZYbotARM` (MIT).** Not a geometry donor (servo, small), but the
   **best MIT Python *reference* for how to structure a `JointSolver`/`IKSolver`** — analytic FK/IK
   in `kinematic_model.py` with PDF derivations. Copy the pattern.
6. **Thor — `AngelLM/Thor-ROS` (CC-BY-SA-4.0) / `b-adkins/thor_arm_description` (GPL-3.0).**
   Technically excellent (ROS2+MoveIt2+URDF) but **copyleft-encumbered**; reuse by **re-deriving DH
   from the geometry**, not vendoring the URDF.
7. **AR2 / Mirobot / Dummy-Robot — Low.** AR2 has no separable URDF/ROS (use AR3 geometry instead);
   Mirobot is closed commercial firmware; Dummy-Robot has no license and welds IK into firmware.
   None is a clean seam donor.

### Best ROS2 + MoveIt support (maps to PiBot's `pibot/ros2/` bridge)

Verified ROS2 + MoveIt2 (not ROS1):

- **AR4** — `ycheng517/ar4_ros_driver` (MIT): full `ros2_control` + MoveIt2 + MoveIt Servo + Pilz.
  **The strongest ROS2 case** and actively maintained (pushed 2026-04).
- **Thor** — `AngelLM/Thor-ROS` (CC-BY-SA-4.0): ROS2 Humble + MoveIt2 + Asgard React GUI (copyleft).
- **Arctos** — `cr0Kz/ros2_arctos` (Apache-2.0): ROS2 `ros2_control` + MoveIt2 over CAN.
- **AR3** — ROS2 only via `RIF-Robotics/ar3_moveit2_config` (MoveIt2, license unstated); core is ROS1.
- **Moveo / Mirobot** — primarily ROS1; community ROS2 forks exist but are small/less proven.

### Cleanest DH/URDF for an ikpy-style Python IK (maps to the `JointSolver` seam directly)

- **AR3 `ar3.urdf`** — plain URDF, MIT → `ikpy.Chain.from_urdf_file()` in one line. **Cleanest.**
- **AR4 `annin_ar4_description`** — xacro, MIT → one expansion step, then ikpy. **Most maintained.**
- **Moveo `moveo_urdf`** — URDF + meshes, MIT, 5-DOF. **Cleanest 5-DOF.**
- **Arctos `arctos_description`** — URDF, Apache-2.0 → use if going the ROS2-bridge route.
- **EEZYbotARM `kinematic_model.py`** — not a URDF, but the **reference Python IK structure** to
  mirror in PiBot's seam.

---

## Bottom line for PiBot integration

- **Two distinct reuse paths exist and both are best served by the AR-family arms:**
  - **Python-IK / solver-seam path:** lift the **AR3 (MIT plain `ar3.urdf`)** or **AR4 (MIT xacro)**
    URDF into `ikpy`, wrap with a rad→deg + joint-reorder shim → a PiBot `IKSolver` that satisfies
    `solve(pose) -> {joint_id: degrees}`. Moveo (MIT) is the cleanest 5-DOF alternative and its
    Arduino driver is the conceptual twin of PiBot's `ArmManager`.
  - **ROS2-bridge path:** AR4 (MIT) is the strongest; Arctos (Apache-2.0) and Thor (copyleft)
    follow. PiBot's `pibot/ros2/` bridge could consume their MoveIt2 plans.
- **Protocol is a non-blocker.** PiBot flashes its own firmware and keeps ASCII+CRC; it reuses
  geometry, not the wire format. AR-family arms even *use* an ASCII-degrees serial already, so a
  shim to PiBot's line+CRC is trivial.
- **Watch the licenses:** AR3/AR4/Moveo = **MIT**, Arctos = **Apache-2.0** (all clean). Thor =
  **CC-BY-SA-4.0 + GPL-3.0** (copyleft — re-derive DH instead of vendoring). Dummy-Robot = **no
  license** (unusable). Mirobot core = **commercial/closed** (community wrappers MIT only).
