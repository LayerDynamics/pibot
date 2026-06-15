# SPEC-4 — PiBot Robot Arm

| | |
|---|---|
| **Spec ID** | SPEC-4 |
| **Title** | PiBot Robot Arm — close the loop from a built, safety-correct stepper arm to a controllable, programmable, kinematics-aware manipulator |
| **Status** | Draft |
| **Version** | 1.0 |
| **Author** | Ryan O'Boyle (`durbanpoisonpew@protonmail.com`) + Claude |
| **Created** | 2026-06-15 |
| **Depends on** | [SPEC-1](SPEC-1-pibot-control-suite.md) (M0–M6, shipped — CLI, `pibotd`, transport, safety, telemetry, deploy); [SPEC-3](SPEC-3-pibot-mission-control.md) (Mission Control desktop app + loopback sidecar) |
| **Realizes** | the gap analysis in [`docs/research/stepper-robot-arms-github/OtherArms.md`](../research/stepper-robot-arms-github/OtherArms.md) §6A (roadmapped deferrals) + §6B (genuinely-unaddressed gaps); supersedes/extends the phased build in [`docs/plans/2026-06-13-pibot-arm-control.md`](../plans/2026-06-13-pibot-arm-control.md) (A.1–A.5) |
| **Target repo** | `/Users/ryanoboyle/pibot` |
| **Robot platform** | Raspberry Pi 5 (8 GB) + 1–2× **Creality 4.2.2** (STM32F103RE) joint controllers over USB-serial UART; reached over the Nebula overlay |
| **Primary host** | MacBook Pro M4 Max (macOS, Apple Silicon) — runs the `pibot` CLI and Mission Control |

> PiBot's arm is **built and safety-correct but only half-wired**: the firmware and `ArmManager`
> already speak a full joint-motion vocabulary (`jpos/jvel/jstop/home/estop/enable/move_synchronized`)
> with unit tests, yet **nothing exposes it** — the entire `pibotd → Mission-Control → CLI → UI`
> surface is read-only telemetry. This spec wires the existing motion engine end-to-end, then adds the
> capabilities a real manipulator needs — gripper control, an in-tree kinematic model, IK/FK behind the
> existing solver seam, coordinated trajectories & teach/playback programs, and a live 3-D twin —
> **without rebuilding PiBot's two best-in-class assets: the layered firmware-independent safety and
> the design-time sizing calculator.**

---

## 1. Background

### 1.1 Problem Statement
PiBot now has a 5–6 DOF open-loop stepper arm whose joints are split across one or more Creality 4.2.2
boards running custom PiBot firmware (`firmware/pibot_arm_stm32`). The firmware is a deliberately dumb,
per-joint primitive engine (position + velocity + homing + safety); the host `pibot.arm` package routes
logical joints to `(board, channel)` and aggregates telemetry. **The architecture is sound and the
hard parts are done — but the arm is not yet usable as a product.** A comprehensive comparison against
27 open-source reference arms (`OtherArms.md`) found PiBot ahead on safety and design tooling but
missing the entire control/kinematics/teach/visualization surface that every functional arm in the
corpus exposes through *some* interface. This spec closes those gaps.

### 1.2 Current State (verified, 2026-06-15)
Shipped and tested today:

- **Firmware** (`firmware/pibot_arm_stm32/pibot_arm_stm32.ino`): `AccelStepper` per joint; **position**
  (`cmd_jpos`), **velocity/jog** (`cmd_jvel`), **homing** (endstop seek → travel-guard → backoff). 3
  homed joints/board (X/Y/Z endstops). **Safety:** soft limits (`clampf`), **latched e-stop**
  (`estop` / `set,_,0`), **300 ms host-quiet watchdog** (HOLD policy — steppers stay energized),
  **fail-closed home fault**, homing required before absolute moves. CRC-8 ASCII protocol
  (`protocol.{h,cpp}` ↔ `pibot/protocol/codec.py`); verbs `jpos jmove jvel jstop home estop set enable
  ping`; telemetry `joints,d0..dN` @ 100 ms.
- **Host routing** (`pibot/arm/manager.py`): `ArmManager` — logical→`(board,channel)` map
  (`linear_joint_map`), per-board sequence, command fan-out, **`move_synchronized`** (speed-scaled
  synchronized arrival), `estop`/`clear_estop`/`enable` broadcast, telemetry drain + re-key.
- **Kinematics seam** (`pibot/arm/kinematics.py`): `JointSolver` Protocol; `DirectSolver`
  (range-checked joint pass-through); `NamedPoseSolver` (static in-code presets). **No IK/FK yet** —
  the seam is intentionally empty (kinematics.py:12–14).
- **Design-time sizing** (`pibot/arm/sizing.py`): robot-agnostic calculator → torque/inertia, motor +
  gear selection, resolution/speed/step-rate, driver current/PSU, stress-and-deflection link
  cross-section, CAD dims, and emits the firmware `JCFG[]` block. TOML config + `python -m
  pibot.arm.sizing`. **Unique in the corpus — preserved unchanged.**
- **Agent** (`agent/app.py`, `agent/pibotd.py`): `build_arm()` from config; `_arm_drain` caches joint
  angles; **`GET /arm/telemetry`** is the *only* arm route. Arm is an optional peripheral.
- **Mission Control** (`pibot/mc/routes_arm.py`): **`GET /api/arm/telemetry`** proxy via
  `RobotLink.arm_telemetry()` → `AgentClient.arm_telemetry()`. No motion route.
- **Desktop app** (`app/src/screens/Arm.tsx`, `stores/armStore.ts`): **read-only** joint-angle bars +
  freshness badge, 250 ms poll. No controls.
- **Config** (`pibot/config.py:55–61`): `arm_serial_ports`, `arm_joints_per_board`, `arm_baud`,
  `arm_encoding`.
- **ROS2 bridge** (`pibot/ros2/bridge.py`): wheeled-robot `/cmd_vel` + telemetry only — **no arm/joint
  topics** (out of scope for the arm by design).

### 1.3 Target Users
- **Operator** (primary): drives/poses the arm from Mission Control or the CLI, teaches and replays
  pose programs, watches the live 3-D twin. One operator, one arm.
- **Developer/integrator**: scripts the arm via the `pibot` CLI and `AgentClient`, plugs new solvers
  into the `JointSolver` seam, sizes a new arm with the sizing calculator.
- **Autonomy/AI layer** (future consumer): emits Cartesian or joint intents that flow through the same
  safety-gated control surface this spec defines.

### 1.4 Motivation
The motion engine already exists and is unit-tested; wiring it is the highest-leverage, lowest-new-logic
work in the project (`OtherArms §10`). Until the control surface, a kinematic model, and persistence
exist, the arm cannot jog from the UI, cannot move to a Cartesian pose, cannot remember a pose, and
cannot be seen in 3-D — i.e. it is not yet the manipulator the hardware can support. `6AR`
(`OtherArms §8`) proves the exact Pi-brain + MCU + JSON/serial + React-UI progression on the same
frontend toolkit, while PiBot already has the *better* safety model — so the target is well-evidenced.

### 1.5 Assumptions
- The arm hardware is built and sized (link lengths/masses, motor+gear selection) via `sizing.py`; its
  per-joint `JCFG[]` is flashed (the `0x7000` SD-image route, see `CLAUDE.md`).
- A 3+3 joint split across two 4.2.2 boards (or a single ≤4-joint board) is the deployment baseline;
  the spec is parameterized on joint count, not fixed at 6.
- The arm remains an **optional peripheral**: an absent/unplugged board must never take down `pibotd`
  or Mission Control (preserve the `build_arm() → None` path).
- Motion is **open-loop** (no encoders) — position truth is "homed + commanded steps." This is a
  hardware choice (`OtherArms §6C`), not a gap this spec addresses.
- Mission Control's sidecar stays **loopback-only**; the Rust core retains the e-stop failsafe.

---

## 2. Requirements

### 2.1 Functional Requirements

Each FR cites the `OtherArms.md` gap it realizes.

**Motion control surface (gap §6B-1 + §6A "motion UI"):**
- **FR-1** — `pibotd` exposes a **safety-gated arm control channel**: a WebSocket `/arm/control` that
  accepts command frames (`jpos`, `jmove`, `jvel`, `jstop`, `home`, `enable`, `estop`, `clear_estop`,
  `move` = coordinated multi-joint) and returns `ack`/`nak`, mirroring the robot's `/control` WS.
- **FR-2** — a **host-side arm safety gate** (analogous to `pibot.control.safety`) validates every
  command before it reaches `ArmManager`: joint-id range, per-joint angle/velocity clamping against
  configured limits, e-stop-latched refusal, and homing-required-before-`jpos`. Firmware safety stays
  the final authority; this gate is the redundant host layer.
- **FR-3** — `AgentClient` (`pibot/control/client.py`) and `RobotLink` (`pibot/mc/robot_link.py`) gain
  arm-motion methods (`arm_jog`, `arm_move_joint`, `arm_move_joints`, `arm_home`, `arm_estop`,
  `arm_clear_estop`, `arm_enable`) over the new channel.
- **FR-4** — Mission Control exposes arm-motion routes (`POST /api/arm/jog|move|home|estop|enable`,
  `POST /api/arm/clear_estop`) in `pibot/mc/routes_arm.py`, delegating to `RobotLink` (no motion logic
  in MC — preserve the thin-proxy invariant).
- **FR-5** — a **`pibot arm` CLI subcommand** (`pibot/cli.py`): `pibot arm jog <joint> <dps>`,
  `pibot arm move <joint> <deg> [--speed]`, `pibot arm move-all <j=deg,...> --seconds <s>`,
  `pibot arm home [<joint>|--all]`, `pibot arm estop|clear|enable|disable`, `pibot arm telemetry`,
  `pibot arm pose <name>`, with `--json` support like the rest of the CLI.
- **FR-6** — the `Arm.tsx` screen gains **controls**: per-joint jog (±) and home buttons, a
  go-to-angle field, an arm-wide **E-Stop** button (always visible, latches), enable/disable, and a
  homing-status indicator per joint. `armStore` gains the corresponding action thunks (currently
  read-only).

**Gripper / end-effector (gap §6B-2):**
- **FR-7** — firmware adds a **`grip` (servo PWM) verb** on the spare `E0` channel (no endstop needed)
  plus an optional **digital-output** verb for pneumatic/relay tools, with min/max angle clamps in
  `JCFG`-style config; `grip <deg>` and `tool <0|1>`.
- **FR-8** — `ArmManager.grip(deg)` / `ArmManager.tool(on)` route the new verbs; the control surface
  (FR-1/3/4/5/6) and telemetry expose gripper position/state.

**In-tree kinematic model (gap §6B-4):**
- **FR-9** — a **`pibot/arm/geometry/` package** holds PiBot's arm as a **URDF + a DH table**
  (re-derived for the built arm; an MIT donor URDF — AR3/Moveo — may seed it). The sizing calculator
  emits/aligns the link lengths so geometry and `JCFG[]` stay consistent.
- **FR-10** — `pibot/arm/sizing.py` gains an **`emit URDF/DH`** path (link lengths + joint limits →
  geometry file) so the model is derived from the same source of truth, not hand-maintained twice.

**IK / FK behind the seam (gap §6A — plan A.5):**
- **FR-11** — **forward kinematics**: telemetry joint angles → end-effector Cartesian pose, surfaced in
  `/arm/telemetry`, the CLI, and the UI.
- **FR-12** — an **`IKSolver`** implementing the existing `JointSolver` Protocol: Cartesian pose →
  `{joint_id: degrees}`, loaded from the FR-9 model. Numeric (`ikpy`) is the V1 solver; analytic
  closed-form remains a drop-in behind the same seam (no firmware/`ArmManager` change).
- **FR-13** — IK/FK dependencies (`ikpy`/`numpy`) are an **optional extra** (`pibot[arm-ik]`),
  **lazy-imported** so `pibot.arm` core and the stdlib-light CLI/agent never import numpy at module
  load (mirrors the `[ml]` boundary).
- **FR-14** — **Cartesian jog & move**: the control surface accepts Cartesian intents (pose / delta)
  solved by the `IKSolver` into a `move_synchronized` call.

**Trajectories & teach/playback (gap §6A — plan A.4 — + §6B-3):**
- **FR-15** — **coordinated trajectories** beyond synchronized arrival: trapezoidal joint-space ramps
  and **Cartesian-linear paths with SLERP orientation** (6AR pattern), streamed as timed `jmove`
  frames; optional waypoint blending.
- **FR-16** — **teach & playback with persistence**: record the current pose from telemetry, name it,
  and build ordered **programs** (move-J / move-L / gripper / wait / loop steps); persist poses and
  programs as **JSON on the Pi** (owned by `pibotd`), CRUD'd via the control surface, the CLI, and a
  Mission-Control program panel. Extends `NamedPoseSolver` from in-code presets to loaded/recorded.
- **FR-17** — playback runs through the same safety gate (FR-2) and is **abortable mid-program** by
  e-stop or stop.

**3-D twin (gap §6B-5):**
- **FR-18** — the `Arm.tsx` screen renders a **live 3-D twin**: the FR-9 URDF loaded via
  `urdf-loader` + three.js, joints driven by live telemetry (~30 Hz), color-coding joints near limits,
  with an optional interactive TCP/joint gizmo that emits jog/IK intents through the control surface.

### 2.2 Non-Functional Requirements
- **NFR-1 (safety preserved)** — every new motion path is subordinate to the unchanged firmware safety
  (e-stop latch, 300 ms watchdog, soft limits, homing-required, link-loss stop). The host gate is
  additive/redundant, never a replacement. E-stop must remain reachable even if IK/trajectory code
  faults.
- **NFR-2 (`[ml]`/stdlib-light boundary)** — `pibot.arm` core, the CLI, and `agent` must not import
  numpy/ikpy at module load. IK is behind `pibot[arm-ik]` and lazy-imported; `DirectSolver`/
  `NamedPoseSolver`/`ArmManager`/control surface stay pure-stdlib.
- **NFR-3 (definition of done)** — `bash scripts/check.sh` green (ruff + ruff-format + mypy strict +
  pytest ≥ 80 % coverage over `pibot`+`agent`, **zero skips**); firmware compiles for the STM32 target;
  echo-stand round-trip passes for the new verbs; desktop gate (vitest + tsc + eslint + cargo) green.
- **NFR-4 (hermetic tests)** — all new behavior testable with the `responder`/`loopback` transports and
  `pibot/control/echo.py`; no test depends on real hardware (hardware/toolchain tests stay marked).
- **NFR-5 (optional peripheral)** — absent arm hardware must never break `pibotd`/MC startup; all arm
  routes return a clean "no arm configured" when absent.
- **NFR-6 (latency)** — jog command → motion start ≤ 100 ms over the Nebula overlay; telemetry/twin
  refresh ≥ 10 Hz; IK solve for a 6-DOF pose ≤ 50 ms on the host.
- **NFR-7 (loopback-only MC)** — new MC routes stay on the 127.0.0.1 control plane; no new public
  surface; the Rust e-stop failsafe still caches the endpoint.
- **NFR-8 (docs accuracy)** — `OtherArms.md`, the arm plan, and `CLAUDE.md` are updated in the same
  change that moves a gap from "missing" to "shipped" (per the repo's documentation-accuracy rule).

### 2.3 Constraints
- Controller is the **Creality 4.2.2 (STM32F103RE)**, 4 step/dir channels + shared ENABLE, 3 endstop
  inputs (X/Y/Z); ≤3 homed joints/board → 3+3 split for 6 DOF. Flashing is the `0x7000` SD-image route.
- **Custom PiBot firmware**, not Marlin/GRBL; protocol is CRC-8 ASCII (mirrored host-side).
- **Open-loop** step/dir (no encoders).
- Core runtime is **stdlib-light**; heavy deps live behind extras installed on the robot only.
- Mission Control sidecar is **loopback-only**; frontend is React 19 + TS + Zustand + Tailwind v4 +
  Radix (Vite/Vitest), Rust core (Tauri 2).

### 2.4 Explicit Non-Goals
- **N1 — No ROS/ROS2/MoveIt for the arm.** PiBot is Pi+MCU+CRC+Tauri by design (`OtherArms §6C`). The
  existing ROS2 bridge may *later* publish `sensor_msgs/JointState` as optional interop, but that is not
  in scope.
- **N2 — No closed-loop / encoders.** Actuation platform choice; out of scope.
- **N3 — No Marlin/GRBL firmware.** The small safety-correct firmware is deliberate.
- **N4 — No multi-arm / dual-arm coordination.** One operator, one arm.
- **N5 — No collision-aware motion planning** (self/scene collision avoidance). IK is reachability +
  joint limits only in V1; planning is a possible future spec.
- **N6 — No change to the sizing calculator's math.** It is preserved; only an emit-geometry path is
  added (FR-10).

---

## 3. Architecture

### 3.1 System Overview
The five-layer arm stack from the plan is unchanged; this spec **fills the upper layers and widens the
firmware↔host contract by exactly two verbs (`grip`, `tool`)**, then exposes the whole motion vocabulary
upward.

```
[ Mission Control app: Arm screen — jog/home/e-stop, program editor, 3-D twin ]   ← SPEC-3 app
            │  POST /api/arm/*  ·  GET /api/arm/telemetry            (loopback)
[ MC sidecar: routes_arm.py → RobotLink (thin proxy, no motion logic) ]
            │  WS /arm/control  ·  GET /arm/telemetry  ·  /arm/poses /arm/programs
[ pibotd (agent): arm control route + host safety gate + FK + persistence ]       ← NEW upper half
            │  logical joint / pose intents
[ Kinematics seam (pibot.arm.kinematics): DirectSolver · NamedPoseSolver · IKSolver(ikpy, extra) ]
            │  {joint_id: degrees}
[ ArmManager (pibot.arm.manager): routing · move_synchronized · trajectories · grip/tool ]
            │  per-board CRC frames over serial
[ Joint firmware (Creality 4.2.2): AccelStepper · position/velocity/homing · safety · grip/tool ]
            │  step/dir/enable/PWM
[ Stepper drivers + joints + gripper servo (hardware) ]
```

`pibot/arm/geometry/` (URDF + DH) feeds both the `IKSolver`/FK (host) and the 3-D twin (app); the
sizing calculator emits the link lengths so geometry, `JCFG[]`, and the model share one source.

### 3.2 Component Design
- **`pibot/arm/safety.py` (new)** — host arm safety gate: stateless validators (joint range, angle/vel
  clamp from config, homing-required, e-stop latch mirror) returning accept/clamp/reject; reused by the
  agent route and the CLI.
- **`pibot/arm/trajectory.py` (new)** — trapezoidal joint ramps + Cartesian-linear/SLERP path
  generation → timed `(targets, dt)` frames for `ArmManager.jmove`/`move_synchronized`. Pure-stdlib
  math for joint-space; Cartesian path uses FK/IK (extra) only when invoked.
- **`pibot/arm/kinematics.py` (extend)** — add `ForwardKinematics` and `IKSolver` (numeric, `ikpy`,
  lazy-imported), both consuming the FR-9 model; `NamedPoseSolver` gains load-from-store + record.
- **`pibot/arm/geometry/` (new)** — `pibot_arm.urdf` + `dh.py`/`dh.toml` (re-derived), loader, and a
  `from_sizing()` emitter.
- **`pibot/arm/manager.py` (extend)** — `grip()`, `tool()`, and a `run_trajectory(frames)` executor
  (paced timed frames with abort check).
- **`pibot/arm/programs.py` (new)** — pose/program data model + JSON (de)serialization; recording from
  a telemetry snapshot; program validation.
- **`agent/app.py` (extend)** — `/arm/control` WS handler (frame → gate → ArmManager), `/arm/poses` and
  `/arm/programs` CRUD (JSON persisted under the agent's state dir), FK-augmented `/arm/telemetry`,
  program-runner task (abortable). Keep `_arm_drain` as the sole telemetry reader.
- **`pibot/control/client.py`, `pibot/mc/robot_link.py` (extend)** — arm-motion + pose/program methods.
- **`pibot/mc/routes_arm.py` (extend)** — `POST` motion routes + pose/program proxy routes.
- **`pibot/cli.py` (extend)** — `pibot arm …` subparser.
- **`app/src/screens/Arm.tsx`, `stores/armStore.ts` (extend)** — controls, program panel, 3-D twin
  (`urdf-loader` + three.js); `armStore` motion + pose/program actions.
- **`firmware/pibot_arm_stm32` (extend)** — `grip`/`tool` verbs + gripper config; safety unchanged.

### 3.3 Data Model
- **Joint command frame** (WS `/arm/control`): `{cmd, joint?, deg?, dps?, seconds?, targets?, on?}` →
  `{type: ack|nak, reason?}`.
- **Arm telemetry** (extended): `{enabled, num_joints, positions:{jid:deg}, homed:{jid:bool},
  gripper:{deg, tool}, pose:{x,y,z,rx,ry,rz}?, ts}`.
- **Pose** (`programs.py`): `{name, joints:{jid:deg}, gripper?:deg, created}`.
- **Program**: `{name, steps:[{kind: moveJ|moveL|grip|tool|wait|loop, …}], created}`.
- **Geometry**: URDF (`pibot/arm/geometry/pibot_arm.urdf`) + DH table; link limits mirror `JCFG`
  min/max.
- **Persistence**: poses/programs as JSON files under the agent state dir on the Pi (e.g.
  `~/.pibot/arm/{poses,programs}/*.json`); config via `pibot/config.py` (gripper pins/limits added).

### 3.4 API & Interface Design
- **Agent (pibotd):** `GET /arm/telemetry` (extended); `WS /arm/control`; `GET/POST/DELETE
  /arm/poses[/{name}]`; `GET/POST/DELETE /arm/programs[/{name}]`; `POST /arm/programs/{name}/run`,
  `POST /arm/programs/stop`. Bearer-token auth on all (except `/healthz`).
- **Mission Control:** `GET /api/arm/telemetry` (extended); `POST /api/arm/jog|move|move-all|home|
  estop|clear_estop|enable|grip|tool`; `…/poses`, `…/programs`, `…/programs/{name}/run|stop` proxies.
- **CLI:** `pibot arm {telemetry,jog,move,move-all,home,estop,clear,enable,disable,grip,tool,pose,
  pose-save,pose-list,program-run,program-list}` with global `--json/--timeout`.
- **Firmware verbs (added):** `grip,<deg>` · `tool,<0|1>`. Existing verbs unchanged.

### 3.5 Data Flow
Jog: app/CLI → `POST /api/arm/jog` / `pibot arm jog` → `RobotLink`/`AgentClient` → WS `/arm/control`
frame → host safety gate (FR-2) → `ArmManager.jvel` → CRC frame → board firmware (clamps, watchdog).
Cartesian move: pose intent → `IKSolver.solve` (extra) → `trajectory` frames → `ArmManager.run_trajectory`
→ firmware. Telemetry/twin: boards → `_arm_drain` cache → FK → `/arm/telemetry` → `/api/arm/telemetry`
→ `armStore` → bars + 3-D twin.

### 3.6 Integration Points
- Reuses SPEC-1 transport (`pibot.transport.serial`), protocol/codec, and the agent auth/WS machinery.
- Reuses SPEC-3 sidecar `RobotLink` delegation pattern and the React/Zustand app shell.
- Sizing calculator (`pibot/arm/sizing.py`) integrates via the FR-10 geometry emitter.
- The arm safety gate parallels `pibot.control.safety`; the e-stop participates in the Rust failsafe
  cache like the robot e-stop.

### 3.7 Security Architecture
Bearer-token auth on every agent arm route (reuse existing middleware). MC stays loopback-only. No new
network surface; the arm boards are local serial only. E-stop authorization is intentionally
unguarded-to-stop (anyone connected can halt; clearing requires an explicit command).

### 3.8 Resilience Design
- Absent/failed board → `build_arm()` returns `None`; all arm routes 503 "no arm configured" cleanly.
- Firmware watchdog halts on host silence; host gate refuses motion when e-stop latched or unhomed.
- Program runner is a cancellable task; e-stop/stop aborts mid-step; a faulting IK/trajectory call
  cannot reach the motors without passing the gate.

### 3.9 Observability
Extended telemetry (homed flags, gripper, pose); structured agent logs for gate rejects, home faults,
program start/step/abort; CLI `--json`; the freshness badge already in `Arm.tsx`.

### 3.10 Infrastructure & Deployment
`pibot[arm-ik]` extra added to `pyproject.toml`; installed on the robot via `deploy/requirements.txt`
(host CLI works without it for joint-only control). No new services — the arm rides inside `pibotd`.
Firmware re-flash required for the `grip`/`tool` verbs (unique `.bin` name per the SD-card rule in
`CLAUDE.md`).

---

## 4. Implementation Plan

### 4.1 Build Phases (each independently shippable; `scripts/check.sh` green = done)
Phases extend the existing arm plan (A.1–A.3 shipped: firmware, safety+homing, multi-board ArmManager).

1. **Phase 1 — Motion control surface** (FR-1..FR-6): host safety gate, agent `/arm/control` WS,
   AgentClient/RobotLink methods, `pibot arm` CLI, `Arm.tsx` controls + `armStore` actions. *No new
   motion math — exposes the built engine.*
2. **Phase 2 — Gripper/end-effector** (FR-7, FR-8): firmware `grip`/`tool` verbs + config; ArmManager
   methods; surface + UI exposure; echo-stand round-trip for the new verbs.
3. **Phase 3 — Kinematic model in-tree** (FR-9, FR-10, FR-11): `pibot/arm/geometry/` URDF + DH;
   forward kinematics; sizing→geometry emitter; FK in telemetry/CLI/UI.
4. **Phase 4 — IK behind the seam** (FR-12, FR-13, FR-14): `IKSolver` (ikpy, lazy + `arm-ik` extra);
   Cartesian jog/move through the control surface.
5. **Phase 5 — Trajectories & teach/playback** (FR-15, FR-16, FR-17): trajectory generator; pose/program
   model + JSON persistence; record/replay; abortable program runner; MC program panel + CLI.
6. **Phase 6 — 3-D twin** (FR-18): `urdf-loader` + three.js Arm screen driven by live telemetry +
   in-tree URDF; optional gizmo → control surface.

### 4.2 Testing Strategy
- **Unit:** safety-gate validators; trajectory frame generation; FK against known poses; IK
  round-trip (FK∘IK ≈ identity within tolerance); pose/program (de)serialization.
- **Integration (hermetic):** `responder`/`loopback` + `echo.py` for `/arm/control` (jog/move/home/
  estop), `grip`/`tool` round-trip, program run/abort; MC route → RobotLink → AgentClient proxy tests;
  agent "no arm configured" path.
- **Frontend (vitest):** `armStore` motion + pose/program actions; Arm screen controls render/disable
  states; twin loader (mock telemetry).
- **Firmware (toolchain-marked):** STM32 compile + echo-stand round-trip for `grip`/`tool`.
- **Manual/hardware-marked:** bench-verified jog/home/move/grip on the real arm before closing each
  hardware-affecting phase (per the plan's DoD).

### 4.3 Rollout Strategy
Ship phase-by-phase to `main` behind the existing optional-peripheral gate (no arm → no behavior
change). Firmware change (Phase 2) requires a coordinated re-flash; host phases (1,3,4,5,6) deploy with
`pibot deploy`. The `arm-ik` extra is robot-only.

### 4.4 Operational Readiness
Update `docs/runbooks/` with an arm operation + e-stop-recovery runbook; update `OtherArms.md` /
arm plan / `CLAUDE.md` as each gap closes (NFR-8). Bench-test e-stop latch + watchdog after the Phase 2
firmware re-flash.

---

## 5. Milestones

Continues the global milestone line (SPEC-1 M0–M6, SPEC-2 M7–M11, arm A.1–A.3 shipped). Labeled
`M-ARM-n` and mapped to plan phases.

| Milestone | Realizes | Gap closed | Exit criteria |
|---|---|---|---|
| **M-ARM-1** Motion control surface | FR-1..6 | §6B-1, §6A motion-UI | jog/home/move/e-stop work from CLI **and** Arm screen through the host gate; hermetic tests green |
| **M-ARM-2** Gripper | FR-7,8 | §6B-2 | `grip`/`tool` verbs flashed; gripper controllable + in telemetry; echo round-trip green |
| **M-ARM-3** Kinematic model + FK | FR-9,10,11 | §6B-4 (+ FK part of §6A) | in-tree URDF/DH; live EE pose in telemetry/CLI/UI; sizing emits geometry |
| **M-ARM-4** IK | FR-12,13,14 | §6A (A.5) | Cartesian move/jog via `IKSolver` (extra, lazy); FK∘IK identity test; core still stdlib-light |
| **M-ARM-5** Trajectories + teach/playback | FR-15,16,17 | §6A (A.4) + §6B-3 | record→name→program→replay with JSON persistence; abortable; trapezoidal + Cartesian-linear paths |
| **M-ARM-6** 3-D twin | FR-18 | §6B-5 | live URDF twin in Arm screen at ≥10 Hz; optional gizmo emits intents |

### Dependency Graph
```
M-ARM-1 ─┬─> M-ARM-2  (gripper rides the control surface)
         ├─> M-ARM-5  (programs drive motion through the surface)
M-ARM-3 ─┴─> M-ARM-4 ─> M-ARM-5 (Cartesian paths)
M-ARM-3 ─────────────> M-ARM-6 (twin needs the URDF)
```
M-ARM-1 and M-ARM-3 are the two roots; M-ARM-3 unblocks IK, Cartesian trajectories, and the twin
together (the single highest-fan-out item, `OtherArms §10`).

---

## 6. Success Criteria

### 6.1 Launch Metrics
- An operator can, from Mission Control with no terminal: home the arm, jog each joint, send it to a
  named pose, command a Cartesian move, record a pose, build and replay a program, and e-stop — and see
  it move in the 3-D twin.
- `pibot arm …` performs the same from the CLI.
- `scripts/check.sh` green across host + desktop gates; firmware compiles; echo round-trip green.

### 6.2 Ongoing Monitoring
Gate-reject and home-fault log rates; telemetry/twin refresh rate; IK solve latency; program
run/abort counts.

### 6.3 Remediation Triggers
Any motion that bypasses the host gate or firmware safety → block release. IK/numpy imported by core
CLI/agent at module load → block (NFR-2). Coverage < 80 % or any test skip → block.

---

## 7. Risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Exposing motion erodes the safety story | Med | High | Host gate (FR-2) is additive; firmware stays final authority (NFR-1); e-stop reachable independent of IK/traj; regression tests for gate + latch |
| R2 | IK deps (numpy/ikpy) leak into stdlib-light core | Med | High | `arm-ik` extra + lazy import; import-time test asserts core/CLI/agent don't import numpy (NFR-2) |
| R3 | In-tree URDF drifts from real arm geometry / `JCFG` | Med | Med | Emit geometry from the sizing source (FR-10); limits mirror `JCFG`; FK sanity test vs measured pose |
| R4 | Open-loop pose error makes IK moves inaccurate | High | Med | Document as open-loop reality; require homing before Cartesian moves; keep speeds conservative; (encoders are N2) |
| R5 | Numeric IK unreachable/at-singularity returns bad joints | Med | Med | Reachability + joint-limit check post-solve; reject & report; never send unclamped targets to motors |
| R6 | Servo gripper on E0 (no endstop) over-travels | Low | Med | Firmware angle clamps in config; conservative defaults; bench-verify before close |
| R7 | Program runner blocks the agent event loop | Low | High | Runner is an async cancellable task; `ArmManager` calls via `to_thread`; e-stop preempts |
| R8 | Firmware re-flash (Phase 2) bricks/regresses safety | Low | High | Unique `.bin` name rule (CLAUDE.md); re-bench e-stop+watchdog after flash; SD route keeps bootloader |

---

## 8. Open Questions

| # | Question | Owner | Default if unresolved |
|---|---|---|---|
| OQ-1 | IK solver for V1: numeric `ikpy` vs analytic closed-form re-derived per geometry? | Ryan | **RESOLVED 2026-06-15 (`/lore:plan`): numeric `ikpy`** behind `arm-ik`, lazy-imported; analytic stays a drop-in behind the same seam |
| OQ-2 | Seed geometry for `pibot/arm/geometry/`: re-derive PiBot's own arm, or vendor an MIT donor URDF (AR3 6-DOF / Moveo 5-DOF) as the template? | Ryan | **RESOLVED 2026-06-15 (`/lore:plan`): vendor an MIT donor URDF** (AR3 6-DOF / Moveo 5-DOF), adapt link lengths to PiBot's arm, load via `ikpy.Chain.from_urdf_file`; the sizing emitter (FR-10) keeps the adapted dims aligned with `JCFG` |
| OQ-3 | Gripper actuation: servo on E0 only, or also a digital-output pneumatic/relay channel? | Ryan | **Servo on E0** (FR-7), digital-out added if a pneumatic tool is used |
| OQ-4 | Exact joint count for the first real build (5 vs 6) and the board split? | Ryan | **6 DOF, 3+3 across two 4.2.2 boards** (plan baseline) |
| OQ-5 | Should the ROS2 bridge later publish `JointState` for the arm (optional interop)? | Ryan | **Deferred** (N1) — not in this spec |
| OQ-6 | Program persistence location/format — agent state dir JSON vs a single TOML, and synced to the host? | Ryan | **Per-item JSON under the agent state dir** on the Pi (FR-16) |

---

## Appendices

### Appendix A — Glossary
- **Joint frame / logical joint** — `J0..J5`, mapped to `(board, channel)` by `linear_joint_map`.
- **Host gate** — `pibot/arm/safety.py`, the redundant host-side validation layer (FR-2).
- **Seam** — the `JointSolver` Protocol in `kinematics.py`; solvers are interchangeable.
- **JCFG** — the firmware per-joint config block emitted by the sizing calculator.
- **Twin** — the live 3-D URDF render of the arm in the app (FR-18).
- **Pose / Program** — a named joint snapshot / an ordered list of motion steps (FR-16).

### Appendix B — Interface Contracts
- **WS `/arm/control` frame:** `{cmd:"jpos"|"jmove"|"jvel"|"jstop"|"home"|"move"|"grip"|"tool"|"enable"|
  "estop"|"clear_estop", joint?:int, deg?:float, dps?:float, seconds?:float, targets?:{jid:deg},
  on?:bool}` → `{type:"ack"|"nak", reason?:str}`.
- **`GET /arm/telemetry`:** `{enabled:bool, num_joints:int, positions:{jid:deg}, homed:{jid:bool},
  gripper:{deg:float, tool:bool}, pose?:{x,y,z,rx,ry,rz}, ts:float}`.
- **`JointSolver` (existing):** `solve(target) -> {joint_id: degrees}` — `IKSolver` and FK consume the
  FR-9 model.
- **Firmware verbs (added):** `>SEQ,grip,<deg>*CC`, `>SEQ,tool,<0|1>*CC`.

### Appendix C — Decision Log
- **D1** — Wire the existing engine before adding new motion math (M-ARM-1 first): highest leverage,
  lowest risk; the verbs already exist and are tested (`OtherArms §6B-1, §10`).
- **D2** — IK is numeric (`ikpy`) behind an optional `arm-ik` extra, lazy-imported, to preserve the
  stdlib-light core (mirrors the `[ml]` boundary). Analytic solvers remain a future drop-in behind the
  unchanged `JointSolver` seam. (OQ-1.)
- **D3** *(resolved 2026-06-15, `/lore:plan`)* — The in-tree kinematic model **vendors an MIT donor
  URDF** (AR3 6-DOF / Moveo 5-DOF), with link lengths **adapted to PiBot's arm** and loaded via
  `ikpy.Chain.from_urdf_file`; the sizing emitter (FR-10) keeps the adapted dimensions aligned with
  `JCFG`, and the MIT attribution is carried in `pibot/arm/geometry/`. (Supersedes the earlier
  "re-derive own" default; respects the donor licensing rule — MIT geometry is safe to vendor.
  OQ-2, `OtherArms §9`.)
- **D4** — Gripper uses the spare `E0` channel as a servo (no endstop needed), the most common pattern
  in the corpus; digital-out pneumatic is optional. (OQ-3.)
- **D5** — Safety is preserved as a constraint, not rebuilt: firmware remains the final authority; the
  host gate is redundant (NFR-1, `OtherArms §7`).
- **D6** — The sizing calculator's math is untouched; only a geometry-emit path is added (N6, FR-10).
- **D7** — No ROS for the arm (N1); the 6AR architecture (`OtherArms §8`), not the ROS arms, is the
  reference target.

### Appendix D — Runbooks (pointers)
- E-stop & recovery: extend `docs/runbooks/e-stop.md` for the arm boards.
- Arm flashing: `firmware/pibot_arm_stm32/sd/README.md` (the `0x7000` SD route) — re-flash for Phase 2.
- New: `docs/runbooks/arm-operation.md` (home → jog → pose → program → e-stop), authored in M-ARM-1/5.

### Appendix E — Traceability (gap → requirement → component → milestone)

| `OtherArms.md` gap | Requirement(s) | Primary component(s) | Milestone |
|---|---|---|---|
| §6B-1 control surface unwired | FR-1..6 | `arm/safety.py`, `agent/app.py`, `client.py`, `robot_link.py`, `routes_arm.py`, `cli.py`, `Arm.tsx`, `armStore.ts` | M-ARM-1 |
| §6A motion UI deferral | FR-6 | `Arm.tsx`, `armStore.ts` | M-ARM-1 |
| §6B-2 no gripper | FR-7,8 | `pibot_arm_stm32`, `arm/manager.py`, control surface | M-ARM-2 |
| §6B-4 no kinematic model | FR-9,10 | `arm/geometry/`, `arm/sizing.py` | M-ARM-3 |
| §6A FK + A.5 IK | FR-11,12,13,14 | `arm/kinematics.py`, `arm/geometry/`, `pyproject` extra | M-ARM-3 (FK), M-ARM-4 (IK) |
| §6A A.4 trajectories | FR-15 | `arm/trajectory.py`, `arm/manager.py` | M-ARM-5 |
| §6B-3 teach/playback + persistence | FR-16,17 | `arm/programs.py`, `agent/app.py`, MC panel, CLI | M-ARM-5 |
| §6B-5 no 3-D twin | FR-18 | `Arm.tsx` (`urdf-loader`+three.js), `arm/geometry/` | M-ARM-6 |
| §7 strengths (safety, sizing) — **preserve** | NFR-1, N6 | firmware safety, `arm/sizing.py` | all (constraint) |

### Appendix F — Sources
- [`docs/research/stepper-robot-arms-github/OtherArms.md`](../research/stepper-robot-arms-github/OtherArms.md) — the gap analysis this spec realizes (esp. §6A/§6B/§7/§8/§9/§10).
- [`docs/plans/2026-06-13-pibot-arm-control.md`](../plans/2026-06-13-pibot-arm-control.md) — the A.1–A.5 phased build (A.1–A.3 shipped).
- [`docs/plans/2026-06-15-stepper-arm-sizing-spec.md`](../plans/2026-06-15-stepper-arm-sizing-spec.md) — the sizing calculator.
- [SPEC-1](SPEC-1-pibot-control-suite.md), [SPEC-3](SPEC-3-pibot-mission-control.md) — control suite + Mission Control this builds on.
- Verified code: `firmware/pibot_arm_stm32/pibot_arm_stm32.ino`, `pibot/arm/{manager,kinematics,sizing}.py`, `agent/app.py`, `pibot/mc/routes_arm.py`, `pibot/control/client.py`, `pibot/mc/robot_link.py`, `app/src/screens/Arm.tsx`, `pibot/config.py`, `pyproject.toml`.
