# OtherArms.md — what the 27 reference arm codebases have, and what PiBot's arm is missing

> **Companion to** [`resources/arms/README.md`](../../../resources/arms/README.md) and
> [`Report-Final.md`](./Report-Final.md). Those rank the donor repos by *geometry* viability.
> **This doc compares them by _software capability_** and evaluates PiBot's own arm stack against
> them. The donor corpus' stated intent is **"reuse only each arm's geometry and rebuild all other
> logic natively"** — so a feature another arm has is **not automatically a PiBot gap**. The gap
> analysis (§6) deliberately separates *roadmapped deferrals*, *genuinely unaddressed gaps*, and
> *intentional architectural divergence*.

---

## 1. What PiBot's arm is (the thesis)

PiBot's arm is a **5–6 DOF open-loop stepper arm whose joints are split across one or more Creality
4.2.2 (STM32F103) boards**, each running **custom PiBot firmware** (not Marlin), driven from the Pi
by a **deliberately dumb, joint-level wire contract**. The product bet is the inverse of almost every
arm in this corpus: instead of a clever monolithic firmware (Marlin/GRBL) or a clever monolithic host
(ROS/MoveIt), PiBot keeps the firmware a per-joint primitive engine and puts all the "smart" motion
(coordination, kinematics, IK) in **swappable host layers above a fixed firmware↔host boundary**
(`docs/plans/2026-06-13-pibot-arm-control.md`). The arm is also an **optional peripheral** of the
existing `pibotd`/Mission-Control stack, not a separate product.

Two things follow from that thesis and dominate every comparison below:

1. **Safety is layered and firmware-independent** — the single trait PiBot's arm has that *most* of
   these 27 arms lack (§7).
2. **Kinematics is an empty, well-defined seam** — IK/FK are explicitly *deferred*, not *absent by
   oversight* (§6A). Many donors exist precisely to fill that seam with geometry (§9).

---

## 2. Coverage & method (honesty about depth)

The corpus is **~12 GB across 27 repos**; "file by file" over all of it is not literally achievable,
so each repo below is tagged with how deeply it was actually read. Surveys were performed by
read-only agents that returned `file:line` evidence; load-bearing claims were spot-verified.

- **Deep-read (source opened, `file:line` evidence):** moveo, parol6, ar4 (both stacks), ar3, ar2,
  annin-robot-project, thor, arctos, 6ar, dummy, faze4, mirobot, charm, jeffh-mecharm, manuel,
  smallrobotarm, martin-ansteensen, danieljhand-6dof, open6x, mariohany-6dof (MATLAB).
- **README + geometry census only (pure-CAD, little/no software):** betabots, mantis, rr1,
  gouldpa-cycloidal, palletizer-hackaday, rebot-devarm.
- **PiBot's own arm: fully read** (firmware, `pibot/arm/`, agent, MC, app, config, tests) — §3.

**Four false premises the survey corrected** (recorded so they don't propagate):
- **PAROL6** has no in-tree GUI — the 962 HTML / 478 JS files are vendored **TMCStepper Doxygen
  docs**; the desktop "commander" app lives in a *separate* repo not cloned here.
- **Arctos** `ros2_arctos/` is an **empty stub** (README + LICENSE only); its only working code,
  `Arctos-ROS/`, is a thinly-renamed **ROS1 fork of BCN3D Moveo** (still MIT © 2018 T. Kitamura).
- **6AR** lists AccelStepper as a dependency but **never uses it** — motion is a custom 100 kHz ISR.
- **faze4**'s IK lives in **binary `.mlx` MATLAB Live Scripts** → IK is *present* but solver type
  is inferred, not source-verified.

---

## 3. What PiBot's arm has today (verified inventory)

| Layer | File(s) | What exists |
|---|---|---|
| **Firmware** | `firmware/pibot_arm_stm32/pibot_arm_stm32.ino` | Custom STM32F103 (Creality 4.2.2). `AccelStepper` per joint; **position** (`cmd_jpos`) + **velocity/jog** (`cmd_jvel`) + **homing** (endstop seek → travel-guard → backoff, `MODE_HOME_SEEK`/`MODE_HOME_BACKOFF`) modes. 3 homed joints/board (X/Y/Z endstops). |
| **Firmware safety** | same | **Soft limits** (`clampf`, jvel stops at boundary once homed); **latched e-stop** (`estop`/`set,_,0`, `dispatch:246-264`); **300 ms host-quiet watchdog** (`WATCHDOG_MS`, HOLD policy — steppers stay energized to resist gravity); **fail-closed home fault** (`homefault` nak if endstop not found within range+margin); homing required before absolute moves. |
| **Protocol** | `protocol.{h,cpp}` ↔ `pibot/protocol/codec.py` | **CRC-8-guarded ASCII** framing (`>SEQ,NAME,ARG*CC`). Commands: `jpos jmove jvel jstop home estop set enable ping`. Telemetry: `joints,d0..dN` @ 100 ms. |
| **Host routing** | `pibot/arm/manager.py` | `ArmManager`: logical joint → `(board, channel)` map (`linear_joint_map`, e.g. 3+3); per-board independent seq; command fan-out; **`move_synchronized`** (speed-scaled so all joints arrive together); `estop`/`clear_estop`/`enable` broadcast to every board; telemetry drain + re-key. |
| **Kinematics seam** | `pibot/arm/kinematics.py` | `JointSolver` Protocol; **`DirectSolver`** (joint-angle pass-through, range-checked); **`NamedPoseSolver`** (static preset poses). **IK/FK intentionally not present** (comment, lines 12–14: "drops into this exact interface once geometry is known"). |
| **Design-time sizing** | `pibot/arm/sizing.py` | **Robot-agnostic stepper-arm sizing calculator** — per-joint worst-case torque (static+dynamic), smallest adequate (motor, gear), angular resolution, achievable speed under the polled step-rate ceiling, driver current + PSU, **link cross-section sized for both bending stress AND tip deflection**, CAD build dims, and **emits the firmware `JCFG[]` block**. TOML config + `python -m pibot.arm.sizing`. |
| **Agent (on-Pi)** | `agent/app.py`, `agent/pibotd.py` | `build_arm()` from config (one `SerialTransport` per board); `_arm_drain` task caches joint angles; **`GET /arm/telemetry`** (`{enabled, num_joints, positions, ts}`) — the *only* arm route. Arm is an optional peripheral (absent board → "no arm", agent keeps serving). |
| **Mission Control** | `pibot/mc/routes_arm.py` | **`GET /api/arm/telemetry`** — thin proxy of pibotd via `RobotLink.arm_telemetry()` → `AgentClient.arm_telemetry()`. No motion route. |
| **Desktop app** | `app/src/screens/Arm.tsx`, `stores/armStore.ts` | **Read-only** live joint-angle bars + freshness ("live"/"stale") badge, polled at 250 ms. No jog/home/e-stop controls (store has no motion actions — verified). |
| **Config** | `pibot/config.py:55–61` | `arm_serial_ports`, `arm_joints_per_board`, `arm_baud`, `arm_encoding`. |
| **Tests** | `tests/test_arm_manager.py`, `test_agent_arm.py`, `test_mc_arm.py`, `app/.../armStore.test.ts` | Routing, sync-move, telemetry proxy, drain, store. |

**The load-bearing observation:** PiBot's arm has a **complete joint-motion vocabulary in the firmware
and in `ArmManager` (jpos/jvel/jstop/home/estop/enable/`move_synchronized`)** — but **none of it is
exposed end-to-end.** The whole `pibotd → MC → CLI → UI` surface is **read-only telemetry**. The
write path exists only as a library with unit tests. (The `pibot/ros2/bridge.py` ROS2 bridge exposes
the *wheeled robot* `/cmd_vel` only — **no arm/joint topics at all**.)

---

## 4. Per-repo capability inventory (what each "other arm" has)

Condensed from the surveys; every functional claim is backed by `file:line` evidence in the agent
reports. Grouped by software depth.

### Tier 1 — full control stacks (ROS or bespoke GUI)

- **moveo (BCN3D Moveo)** · MIT · 5-DOF + servo gripper · Arduino Mega/RAMPS. **ROS1 + MoveIt** (KDL
  numeric IK, RViz+Gazebo). rosserial → AccelStepper+MultiStepper sketch. **Two firmwares**: the
  ROS-driven sketch has *no* homing/e-stop/watchdog; the stock Marlin firmware (homing/M112/watchdog)
  is bypassed by the ROS path. Notable: TensorFlow webcam pick-and-place, espeak TTS.
- **ar4 (Annin AR4)** · two stacks on one arm · Teensy 4.1 (**mandatory encoders, closed-loop,
  latched HW e-stop**) + Nano gripper. **`ar4-hmi/`** (non-commercial): Python/tkinter desktop app,
  **analytic closed-form C++ IK**, joint+Cartesian+tool jog, teach/playback, `.ar4` job language,
  DH/limit calibration UI, overcurrent-protected gripper. **`ar4_ros_driver/`** (MIT): **ROS2 +
  MoveIt2 + ros2_control** (KDL numeric IK, Servo jog, Gazebo+RViz).
- **ar3** · MIT · 6-DOF · Teensy 3.5 · **ROS1 + MoveIt1** (KDL numeric IK, RViz+Gazebo, joystick
  jog). Open-loop (encoders for state/cal only). Gripper declared but not actuated. No firmware
  safety beyond limit-switch homing.
- **arctos** · MIT (inherited) · 6-DOF (driven as 5) + servo gripper · Mega/RAMPS. The advertised
  Apache-2.0 `ros2_arctos/` is an **empty stub** (README+LICENSE only). The only working code,
  `Arctos-ROS/`, is a **thinly-renamed ROS1 fork of BCN3D Moveo** (still MIT © 2018 T. Kitamura;
  `moveo_moveit` msg pkg intact): **ROS1 + MoveIt1** (KDL numeric IK, RViz+Gazebo, OMPL/CHOMP/Pilz
  pipelines), rosserial → AccelStepper+MultiStepper sketch, RC-servo gripper on pin 11. **Default
  launch runs fake controllers**; blocking non-interruptible motion; **no firmware safety** (no
  e-stop/limits/watchdog/homing). The "ROS2 over CAN, closed-loop" pitch exists only as the stub's
  README aspiration.
- **ar2** · non-commercial · 6-axis (+track) · Mega 2560 · **Python 2.7/Tkinter** desktop app with
  **analytic IK in pure Python** (`CalcRevKin`), joint+Cartesian jog, teach/playback, a real job
  language (Call/Return, IO/If-Jump, registers, vision), pickle job files. Bit-banged steppers, no
  stepper lib, no CRC/watchdog/e-stop. DH table in code; **no URDF**.
- **thor (AngelLM)** · CC-BY-SA · 6-DOF + 1-DOF mimic gripper · Arduino/GRBL **or** RepRapFirmware
  board · **ROS2 Humble + MoveIt2 + ros2_control** (KDL numeric IK), g-code over serial. **"Asgard"
  React web teach-pendant** (FK/IK jog, MOVE J/L, localStorage programs, Three.js twin) + RViz+Gazebo.
- **parol6** · GPLv3 · 6-DOF · **STM32F446** · AccelStepper + TMC5160 (SPI), **3 Mbaud custom binary
  USB protocol** (CRC byte sent but never validated), **CAN-bus smart gripper**, elaborate
  limit-switch homing. Kinematics/GUI are in *separate* repos (`PAROL-commander-software`,
  `PAROL6-python-API`, `PAROL6-ROS2-MOVEIT`); in-tree only a Leap-Motion teleop demo (roboticstoolbox
  numeric IK + `jtraj`). Safety is hardware-e-stop + host-side, **not** firmware-enforced.
- **6ar** · 6-DOF · **Teensy 4.1 + Raspberry Pi 5 + JSON-over-serial + React/TS web app** — the
  closest architectural twin to PiBot (see §8). Host-side numeric IK (roboticstoolbox `ikine_LM`),
  trapezoidal+SLERP trajectories, block-program editor, in-browser URDF digital twin, pneumatic
  relay gripper. Latched HW e-stop in firmware; **link-loss handled host-side only** (ACK timeout →
  `StopAll`). Custom 100 kHz step ISR (not AccelStepper).
- **dummy (Dummy-Robot)** · no license · 6-DOF + CAN gripper · **2-MCU: STM32F405 kinematics brain +
  N× STM32F103 closed-loop FOC joint drivers over CAN** (MT6816 magnetic encoders). **Analytic
  closed-form IK** (Pieper, 8 configs) on the brain. ODrive/fibre lineage; odrivetool-fork CLI;
  Unity "DummyStudio" host (binary, unverified). Switch-less absolute-encoder homing. `EmergencyStop`
  but no watchdog. DH hard-coded in C++; no URDF.

### Tier 2 — partial / single-layer control

- **faze4** · CERN-OHL-S · 6-DOF · Teensy · **MATLAB** offline (Peter Corke toolbox) computes
  trajectories → streamed as binary frames to a custom timer-based step firmware. FK + IK present
  (IK in binary `.mlx`). Limit-switch homing + error-lock; digital on/off gripper. ROS1 URDF/Gazebo
  artifacts. No host GUI.
- **mirobot** · MIT · 6-DOF WLKATA (vendor G-code controller; firmware not in repo) · **ROS2** bridge
  (C++) emitting G-code; **RMPflow** numeric IK *configured but not wired*; **NVIDIA Isaac Sim**
  attractor demo + RViz2 sliders. Gripper modeled but not actuated.
- **charm** · GPLv3 · 5-DOF chess arm · Arduino Uno + PCA9685 servos · **analytic trig IK** (test
  scripts), **per-square teach tables**, 4-state pick/place machine. App layer = chess engine
  (Stockfish/α-β) + **64 reed-switch board sensing**. No ROS, no jog, no firmware safety.
- **manuel** · MIT · 6-DOF + gripper · **Dynamixel** smart servos via U2D2 (host Python, Dynamixel
  SDK). **Only genuinely closed-loop arm here via servo feedback.** **Teach-by-backdrive** (torque
  off → hand-pose → record). No kinematics (joint-space only), no GUI, no ROS. URDF for viz only.
- **martin-ansteensen** · no license · 6-DOF · Mega/RAMPS + Pi camera · Python host with **analytic
  IK (vector-geometry, non-DH "glumb" cascade)**, AccelStepper firmware, multi-pass limit homing,
  OpenCV vision pick-and-place, servo gripper. Console/OpenCV UI (no windowed GUI).
- **danieljhand-6dof** · CC-BY-NC (README) · 6-DOF · Teensy 4.1 · AccelStepper firmware + **Flask +
  SocketIO web GUI** (per-joint sliders, save/recall poses, e-stop button, live console).
  **FK-only with user-editable DH** in the UI; **IK explicitly stubbed** ("not implemented").

### Tier 3 — on-MCU IK reference / minimal

- **smallrobotarm (Skyentific)** · GPLv3 · 6-DOF · Mega 2560 · **the cleanest analytic-IK + DH
  reference in the corpus**, all on an 8-bit AVR (`Simple6DoFVer1.2.ino:594-598` DH table; full
  4×4 homogeneous-transform + spherical-wrist decoupling). Cartesian-linear trapezoidal trajectory.
  No host, no GUI, no safety, no gripper.
- **open6x** · MIT · 6-DOF + servo gripper · Mega/RAMPS · **full analytic IK on the Arduino (8
  closed-form solutions), DH-based FK, AccelStepper, hardware e-stop ISR, homing** — the most
  complete self-contained MCU stepper stack. No host/GUI.
- **mariohany-6dof** · no license · 6-DOF · **MATLAB** (Peter Corke) — DH FK + **both analytic
  (law-of-cosines) and numeric (Jacobian pseudo-inverse / resolved-rate) IK**, singularity treatment.
  Densest CAD (94 SLDPRT). ROS/URDF *described but not in repo*. No firmware, no GUI.
- **jeffh-mecharm** · MIT · 4-DOF + gripper · **Pico/RP2040 MicroPython** + PCA9685 SG90s · joystick
  teleop with soft-PID smoothing. **No kinematics**, no ROS, no GUI.
- **annin-robot-project** · GPLv3 · 6-axis · Mega-class · the AR-family ancestor: Python2/Tkinter +
  bit-banged 9600-baud firmware. **Zero kinematics** (joint-space only), no homing/e-stop/watchdog.
  Teach/playback + pickle jobs.

### Tier 4 — pure-CAD geometry donors (no control software in-repo)

- **rr1 (Real Robot One)** · AGPL · 6-axis · **227 STL + 61 FreeCAD**; designed for closed-loop
  (per-joint AMT encoders) but no controller code ships. Largest STL donor.
- **betabots** · GPLv3 · 6-DOF · 481 IPT + 9 STP (Moveo's ancestor lineage); 3-finger gripper CAD.
- **mantis** · GPLv3 · 6-DOF · 209 IPT + 1 STP (successor to betabots).
- **rebot-devarm (Seeed reBot)** · CERN-OHL-W + Apache · 6-DOF + gripper · **CAN quasi-direct-drive
  servos** (Damiao/Robstride); 56 STEP. All software (ROS2/MoveIt2/Pinocchio/LeRobot/Web UI) is in
  *external* repos — geometry+docs only in-tree.
- **gouldpa-cycloidal** · no license · cycloidal-drive actuator CAD (49 IPT, Inventor-only). The
  lone cycloidal donor.
- **palletizer-hackaday** · no license · **3-DOF parallelogram palletizer** · 1 monolithic STEP. The
  lone non-articulated topology.

---

## 5. Cross-cutting capability matrix

Legend: ✓ yes · ◐ partial/demo/staged · ✗ no/none · `—` not applicable. IK column: **A**=analytic
closed-form, **N**=numeric (KDL/MoveIt/ikpy/roboticstoolbox), **A+N**=both. FW-safety = *firmware-
independent* safety (e-stop / limits / watchdog / homing, on the MCU).

| Repo | DOF | Controller | FK | IK | GUI | Jog | Teach/play | Traj | ROS/MoveIt | Gripper | Closed-loop | Sim/viz | FW-safety | Geometry |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **PiBot (today)** | 5–6 | 4.2.2 STM32F1 | ✗ | ✗ *(seam)* | ◐ read-only | lib-only | ◐ presets | ◐ sync-move | ✗ *(robot only)* | ✗ | ✗ | ◐ bars | **✓✓ layered** | (donor) |
| moveo | 5 | Mega/RAMPS | ✓ | N | ◐ RViz | ◐ | ◐ hardcoded | ✓ | ROS1+MoveIt | ✓ servo | ✗ | ✓ RViz+Gz | ✗ (ROS path) | URDF/STL |
| ar4-hmi | 6 | Teensy4.1 | ✓ | **A** | ✓ tkinter | ✓ +tool | ✓ jobs | ◐ | ✗ | ✓ | **✓ enc** | ✗ | ◐ HW e-stop | DH |
| ar4-ros | 6 | Teensy4.1 | ✓ | N | ◐ RViz | ✓ Servo | ✗ | ✓ | **ROS2+MoveIt2** | ✓ | **✓ enc** | ✓ Gz+RViz | ◐ HW e-stop | URDF/STL |
| ar3 | 6 | Teensy3.5 | ✓ | N | ◐ RViz | ✓ | ✗ | ✓ | ROS1+MoveIt | ✗ decl | ✗ | ✓ Gz+RViz | ✗ homing | URDF/STL |
| arctos | 6→5 | Mega/RAMPS | ✓ | N | ◐ RViz | ✓ | ✗ | ✓ | ROS1+MoveIt1 | ✓ servo | ✗ | ✓ RViz+Gz | ✗ | URDF/STL |
| ar2 | 6 | Mega | ✓ | **A** | ✓ Tk(Py2) | ✓ | ✓ jobs | ◐ | ✗ | ✓ | ✗ | ✗ | ✗ homing | DH |
| thor | 6 | GRBL/RRF | ✓ | N | ✓ React web | ✓ | ✓ localStorage | ✓ | **ROS2+MoveIt2** | ✓ | ✗ | ✓ Three+Gz | ◐ in fw repo | URDF/STEP |
| parol6 | 6 | STM32F446 | ✓* | N* | ✗ (sep repo) | ✓ | ✗ (sep repo) | ◐ | sep repo | ✓ CAN | ✗ | ◐ matplotlib | ◐ host/HW | URDF/DH |
| 6ar | 6 | Teensy4.1+Pi5 | ✓ | N | **✓ React web** | ✓ | ✓ blocks | ✓ SLERP | ◐ artifacts | ✓ pneum | ◐ drive-lvl | **✓ URDF twin** | ◐ HW e-stop | URDF/STL |
| dummy | 6 | F405+N×F103 | ✓ | **A** | ◐ Unity bin | ✓ | ◐ | ◐ ToDo | ✗ | ✓ CAN | **✓ FOC** | ◐ OLED | ◐ e-stop | DH(code) |
| faze4 | 6 | Teensy | ✓ | (in .mlx) | ✗ MATLAB | ✓ | ✓ | ✓ | ROS1 artifacts | ✓ digital | ✗ | ✓ MATLAB+Gz | ◐ limit lock | URDF/DH |
| mirobot | 6 | vendor box | ✓ | ◐ RMPflow | ✓ RViz2 | ✓ | ✗ | ✓ | **ROS2** | ◐ modeled | ✗ | ✓ IsaacSim | ✗ (vendor) | URDF/USD |
| charm | 5 | Uno+PCA9685 | ✓ | **A** | ✗ | ✗ | ✓ tables | ✓ | ✗ | ✓ servo | ✗ | ✗ | ✗ | STEP |
| manuel | 6 | U2D2 host | ✗ | ✗ | ✗ | ✓ | ✓ backdrive | ✗ | ✗ | ✓ | **✓ servo** | ✗ | ◐ servo lim | URDF |
| martin-ans. | 6 | Mega/RAMPS | ✓ | **A** | ◐ console | ✓ | ✗ | ◐ | ✗ | ✓ servo | ✗ | ◐ OpenCV | ✗ homing | STEP |
| danieljhand | 6 | Teensy4.1 | ✓ | ✗ stub | **✓ Flask web** | ✓ | ✓ poses | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | STEP |
| smallrobotarm | 6 | Mega | ✓ | **A** | ✗ | ✗ | ✗ | ✓ lin | ✗ | ✗ | ✗ | ✗ | ✗ | STEP/DH |
| open6x | 6 | Mega/RAMPS | ✓ | **A**(8) | ✗ | ✓ | ✗ | ✓ | ✗ | ✓ servo | ✗ | ✗ | ✓ e-stop ISR | STEP/DH |
| mariohany | 6 | (planned) | ✓ | **A+N** | ✗ MATLAB | ✗ | ✗ | ✓ rr | described | ✗ | ✗ | ✓ MATLAB | ✗ | SLDPRT/DH |
| jeffh-mecharm | 4 | Pico µPy | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✓ | ◐ soft-PID | ✗ | ✗ | STEP |
| annin-project | 6 | Mega | ✗ | ✗ | ✓ Tk(Py2) | ✓ | ✓ | ◐ | ✗ | ✓ servo | ✗ | ✗ | ✗ | STEP/STL |
| rr1 | 6 | (none in repo) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ CAD | (designed) | ✗ | ✗ | 227 STL |
| betabots | 6 | (none) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ CAD | ✗ | ✗ | ✗ | IPT/STEP |
| mantis | 6 | (none) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ CAD | ✗ | ✗ | ✗ | IPT/STEP |
| rebot-devarm | 6 | CAN (ext SW) | ext | ext | ext web | ext | ext LeRobot | ext | ext ROS2 | ✓ | ✓ (ext) | ext Isaac | ext | 56 STEP |
| gouldpa | ? | (none) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | IPT |
| palletizer | 3 | (none) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 1 STEP |

\* parol6 FK/IK/teach exist only in its **separate** commander/API repos, not this checkout.

---

## 6. Gap analysis — what PiBot's arm is missing

Split per the donor-corpus intent: a feature another arm has is a **gap** only if it is neither
already planned nor an intentional architecture choice.

### 6A. Roadmapped deferrals (in the plan — *not* oversights)

These are absent today **on purpose**, with a numbered home in
`docs/plans/2026-06-13-pibot-arm-control.md`. The right comparison is "which donor fills the seam,"
not "PiBot is behind."

| Deferred capability | Plan phase | Status in PiBot | Who fills the seam |
|---|---|---|---|
| **IK (Cartesian pose → joints)** | **A.5** | `JointSolver` seam ready; `IKSolver` not written (kinematics.py:12–14) | Analytic donors: smallrobotarm, open6x (8-soln), ar2/ar4-hmi, dummy. Numeric: moveo/ar3/ar4-ros/thor (KDL), 6ar/parol6 (roboticstoolbox), `ikpy` per donor README. |
| **FK (joints → Cartesian)** | implied by A.5 | none | Same donors (every Tier-1/2 arm has FK). Needed for telemetry→pose. |
| **Coordinated trajectories / blending / waypoint programs** | **A.4** | `move_synchronized` (synchronized arrival) exists in `ArmManager`; no blending/waypoints | 6ar (trapezoidal+SLERP), thor/moveo (MoveIt), faze4 (offline arrays), smallrobotarm (Cartesian-linear). |
| **Motion control UI (jog / home / e-stop buttons)** | "later, hardware-gated milestone" (Arm.tsx header) | UI is read-only | danieljhand (Flask sliders), 6ar/thor (web pendant), ar4-hmi/ar2 (desktop). |

### 6B. Genuinely unaddressed gaps (the high-value findings)

These are *not* in the plan as written and *not* architectural exclusions — they're the substantive
missing pieces.

1. **No exposed arm-motion control surface, end-to-end.** ✅ **SHIPPED (M-ARM-1, 2026-06-15).** The
   firmware and `ArmManager` already had the full motion vocabulary (`jpos/jvel/jstop/home/estop/
   enable/move_synchronized`) with unit tests; M-ARM-1 wired it end-to-end behind a new **host arm
   safety gate** (`pibot/arm/safety.py` — per-joint clamp, e-stop-latched refusal, homing-required):
   agent `WS /arm/control`, `AgentClient`/`RobotLink` motion methods, MC `POST /api/arm/*` routes, a
   `pibot arm` CLI subcommand (jog/move/move-all/home/estop/clear/enable/disable/pose/telemetry), and
   `Arm.tsx` controls (per-joint jog/home, go-to-angle, latching E-Stop, homed indicators). See
   [`docs/runbooks/arm-operation.md`](../../runbooks/arm-operation.md). *(Originally: the motion engine
   was built but unwired — reachable only from Python tests — "implemented but never called.")*

2. **No gripper / end-effector control.** The firmware, `ArmManager`, protocol, and config have **no
   gripper concept**, and the spare `E0` channel called out in the plan is unused. Nearly every
   functional donor controls one: servo (moveo, ar-family, charm, martin-ansteensen, open6x,
   mecharm), digital/pneumatic (faze4, 6ar), CAN smart-gripper (parol6, dummy), or Dynamixel
   (manuel). `sizing.py` computes an `end_effector_arc_mm` but there is no actuation.

3. **No teach & playback / pose programs / persistence.** `NamedPoseSolver` holds **static presets
   defined in code** — there is no record-from-current-pose, no replay sequence, no program/job
   editor, and no on-disk persistence. Donors with real teach/playback: ar2 & ar4-hmi (full job
   languages with IO/branch/registers), 6ar (drag-drop block programs), thor (localStorage),
   danieljhand (save/recall), manuel (teach-by-backdrive), charm (per-square tables), faze4 (waypoint
   arrays).

4. **No kinematic model / geometry artifact wired into the tree.** PiBot deliberately treats these
   repos as *geometry donors*, but **no URDF or DH table is yet present in the PiBot tree** —
   `sizing.py` takes link lengths for *torque/CAD* math, not a kinematic chain. This is the concrete
   bridge between the "reuse geometry" intent and actually shipping IK/FK/sim (§6A, §9). Until a
   model lands, A.5 cannot start.

5. **No 3D visualization / digital twin.** `Arm.tsx` shows joint-angle bars only. The most relevant
   comparators render the live pose: 6ar (in-browser URDF twin via `urdf-loader`+three.js — and
   PiBot's app is *already* React+three-capable), thor (Three.js + RViz), moveo/ar3/ar4/mirobot
   (RViz/Gazebo/Isaac), parol6/faze4/mariohany (matplotlib/MATLAB).

### 6C. Intentional architectural divergence (*not* gaps — recorded so they aren't mistaken for gaps)

- **No ROS / ROS2 / MoveIt for the arm.** PiBot is Pi + MCU + custom CRC protocol + Tauri **by
  design** (CLAUDE.md). PiBot *does* have a ROS2 bridge (`pibot/ros2/bridge.py`) but it exposes the
  **wheeled robot's `/cmd_vel` + telemetry only — no arm/joint topics**. Donors that are ROS
  (moveo/ar3/arctos = ROS1; ar4-ros/thor/mirobot = ROS2) are *not* a template PiBot should follow.
  Tellingly, **6ar — the closest architectural twin — also deliberately avoids ROS at runtime**
  (its ROS files are unused SolidWorks-export artifacts). *Possible non-gap enhancement:* the
  existing bridge could later publish `sensor_msgs/JointState` and subscribe joint goals, but that
  is optional interop, not a missing core feature.
- **Open-loop, no encoders.** PiBot uses step/dir off the 4.2.2's onboard drivers **by hardware
  choice**. Closed-loop donors (ar4 encoders, dummy FOC/MT6816, manuel Dynamixel, rr1 by-design) are
  a different actuation platform, not a software omission. (A future encoder option is conceivable
  but is a hardware decision.)
- **No clever monolithic firmware (Marlin/GRBL).** Deliberate (plan "Why custom firmware"). The
  moveo finding — that Marlin's safety is *bypassed* when driven over ROS — actually **validates**
  PiBot's choice to own a small, safety-correct firmware.

---

## 7. PiBot's distinctive strengths (what it has that the corpus mostly lacks)

The review must not read as "PiBot is behind." On its core axes it is **ahead** of almost all 27:

1. **Layered, firmware-independent safety is rare here and PiBot has the most complete version.**
   The survey's recurring finding: **most arms have no firmware safety at all** (moveo-ROS, arctos,
   ar2, ar3, annin-project, smallrobotarm, charm, mecharm, faze4-beyond-homing). The few with any
   have a **latched hardware e-stop only** (ar4, 6ar, open6x, dummy) — and **none has a host-quiet
   command-timeout watchdog**. PiBot uniquely combines **soft limits + latched e-stop + 300 ms
   deadman watchdog (HOLD) + link-loss stop + fail-closed homing**, redundant with the rest of the
   PiBot safety stack. This is the standout.

2. **A design-time sizing calculator that no donor has.** `pibot/arm/sizing.py` (torque/inertia →
   motor+gear selection → resolution/speed/step-rate → driver current/PSU → **stress-and-deflection
   link cross-section** → CAD dims → emitted `JCFG[]`) is unique in the corpus. Donors hard-code
   tuned magic numbers; PiBot derives them. This directly serves the "reuse geometry, rebuild
   everything else" thesis — feed a donor's link lengths/masses in, get a buildable, motorized arm
   out.

3. **CRC-guarded, fuzz-hardened wire protocol.** Most donors use unguarded ASCII/G-code/JSON;
   parol6's protocol *has* a CRC byte but **never validates it**. PiBot's CRC-8 framing with
   `DecodeError`-not-crash decoding is more robust than nearly every wire format surveyed.

4. **Multi-board joint fan-out with per-board sequence tracking** (`ArmManager`) — most donors are
   single-MCU; PiBot's clean logical-joint→(board,channel) abstraction across two 4.2.2 boards is
   unusual and matches its commodity-hardware bet.

5. **The firmware↔host contract is the cleanest in the set.** "Dumb joint primitives below, swappable
   smarts above" is exactly the boundary the moveo two-firmware mess and the parol6 split-repo
   confusion show the value of.

---

## 8. The architectural twin to study: 6AR

Of all 27, **`6ar` is the one PiBot should treat as a reference target**, because it is the same
architecture one step further along:

| Axis | 6AR | PiBot today |
|---|---|---|
| Brain | Raspberry Pi 5 | Raspberry Pi 5 |
| Joint controller | 1× Teensy 4.1 (central) | 1–2× Creality 4.2.2 (fan-out) |
| Wire protocol | id-tagged **JSON over serial** + `{cmd,status,id}` ACK | **CRC ASCII** + ack/nak |
| Host bridge | Node.js (owns the port, ACK timeouts → `StopAll`) | `pibotd` aiohttp (owns transport) |
| Kinematics | host-side Python child proc, numeric IK + SLERP | seam ready, **not yet built** |
| UI | **React + Zustand + Tailwind + Radix** web app: jog, block programs, live **3D URDF twin**, persistent E-Stop | **React + Zustand + Tailwind + Radix** app: **read-only bars** |
| Safety | latched HW e-stop (fw); **link-loss host-side only** | latched e-stop + **firmware watchdog** + link-loss (stronger) |

The UI stacks are *nearly identical*. 6AR demonstrates exactly the jog → teach → block-program →
3D-twin progression that fills PiBot's §6A/§6B gaps, on the same hardware and frontend toolkit —
while PiBot already has the **better safety model**. It is the most actionable blueprint in the
corpus, and the `resources/arms/README.md` already flags it as "closest to PiBot's architecture."

---

## 9. When PiBot builds IK (A.5): best kinematic donors

Per the licensing rule in `resources/arms/README.md` (vendor MIT/Apache geometry as-is; **re-derive**
GPL/AGPL/CC-BY-SA/CERN-OHL; reference-only for no-license):

- **Numeric / library route (fastest, matches the seam):** load a clean **MIT URDF** with `ikpy` or
  `roboticstoolbox` and wrap as an `IKSolver`. Cleanest URDFs: **ar3** (`ar3.urdf.xacro`, MIT) and
  **mirobot** (`mirobot_urdf_2_original.urdf`, MIT); **moveo** (`moveo_urdf.urdf`, MIT, 5-DOF) is the
  README's recommended primary. 6ar and parol6 both prove the roboticstoolbox `ikine_LM` path on
  comparable hardware.
- **Analytic closed-form reference (if a hand-rolled solver is wanted):** **smallrobotarm**
  (`Simple6DoFVer1.2.ino:594-598` DH + spherical-wrist decoupling — the cleanest, AVR-proven) and
  **open6x** (8-solution analytic IK + DH FK). Both **GPLv3/MIT respectively → re-derive the DH
  numbers, rewrite the solver in Python.** **dummy** (analytic Pieper, no license → reference only)
  and **ar2/ar4-hmi** (analytic, non-commercial → reference only) corroborate the geometry.
- **DH numbers already extracted by the survey** (facts, freely usable): smallrobotarm
  `r=[47,110,26,0,0,0] d=[133,0,0,117.5,0,28]`; mariohany `a=[37.5,160,15,0,0,0]
  d=[135.8,0,0,138.1,0,28.2]`; parol6 `a1=110.5,a2=23.42,a3=180,a4=43.5,a5=176.35`.

**Prerequisite for all of the above (gap §6B-4):** land *one* geometry artifact (a re-derived URDF or
DH table) in the PiBot tree first — that single step unblocks IK, FK, and a 3D twin together.

---

## 10. How the gaps relate (dependency map, not a prescription)

Observations on how the §6B gaps depend on each other, so they aren't read as five independent items:

- **The control-surface gap (§6B-1) is the only one whose engine already existed — and is now
  shipped (M-ARM-1).** Firmware + `ArmManager` motion verbs were built and unit-tested but unwired;
  M-ARM-1 wired them end-to-end behind a host safety gate, so this is no longer a gap. The remaining
  §6B items below still need new logic.
- **One geometry artifact (§6B-4) is the shared prerequisite for three gaps at once:** IK (plan A.5),
  FK, and a 3D twin (§6B-5) all block on a URDF/DH model being present in-tree. It is the single
  highest-fan-out missing piece, and the donor corpus exists precisely to supply it (§9).
- **Gripper (§6B-2) and teach/playback (§6B-3) are largely independent** of the kinematics chain —
  the gripper needs only the spare `E0` channel + a protocol verb; teach/playback extends
  `NamedPoseSolver` with record/replay + persistence (6ar's block model is the in-corpus template).
- **The "later UI milestone" deferral (§6A) collapses into §6B-1 and §6B-5** — once a control surface
  and a model exist, the read-only `Arm.tsx` becomes a jog/teach/twin panel. The **jog/home/move/
  E-Stop** half shipped in M-ARM-1 (`Arm.tsx` now has motion controls); teach/playback (§6B-3) and the
  twin (§6B-5) follow in M-ARM-5/6.

Note for balance: PiBot's **safety model and sizing calculator are already best-in-corpus** (§7) —
they are not gaps and are the foundation the missing pieces would build on, not replace.
