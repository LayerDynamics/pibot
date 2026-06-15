# Plan — Stepper Robot-Arm Sizing Spec + Calculator (configurable, robot-agnostic)

> **For Claude:** a **design/engineering plan**, not a code milestone. It defines (a) a
> RepRap-style engineering **spec** for sizing a DIY stepper-motor robot arm from first
> principles, and (b) a **configurable Python calculator** (`pibot/arm/sizing.py`) that turns
> per-joint inputs into a sizing verdict + the firmware `JCFG[]` numbers. **Generic NEMA17
> 6-DOF baseline; every input is configurable and agnostic of any specific robot.** Full
> derivations + sources live in `docs/research/stepper-arm-sizing/{1..4}-*.md`.

**Goal:** Let a builder design *their own* stepper arm: choose gear ratios, motor frame sizes,
microstepping, speeds, and driver/PSU, by computing — not guessing — every requirement. The
calculator consumes a config (link masses/lengths, payload, reach, target speed/accel, motor
catalog) and emits, per joint: required torque, the smallest adequate `(gear, motor)`, angular
resolution, max feasible joint speed, and the `steps_per_deg / max_sps / accel` to drop into
`firmware/pibot_arm_stm32` `JCFG[]` — plus the arm-level PSU current.

## The chain (how the four domains connect)

```
payload + reach + link masses ─▶ [B] torque per joint (worst case)
                                      │
target joint speed/accel ─────────────┤
                                      ▼
                         pick GEAR RATIO G   ── the dominant lever ──┐
                                      │                              │
        [B] T_motor_req = T_joint/(G·η) ─▶ motor frame (NEMA17/23)   │
        [A] resolution  = 360/(steps·μ·G) ◀──────────────────────────┤  (G sets BOTH)
        [C] top speed   = ω_motor_max / G ◀──────────────────────────┘
                                      │
        [C] step_rate   = joint_deg_s · steps_per_deg  ─▶ check AccelStepper/F103 ceiling
        [D] phase current ─▶ onboard (≤2A) vs external driver ─▶ PSU current
                                      │
                                      ▼
              firmware JCFG[]: steps_per_deg, max_sps, accel  (+ mechanical min/max_deg, home_pos_deg)
```

`G` (gear ratio) is the pivot: it divides required motor torque by `G`, divides reflected
inertia by `G²`, multiplies resolution by `G`, and divides top speed by `G`. **Pick `G` first;
the motor size, resolution, and speed all fall out of it.**

---

## [A] Gear ratio & angular resolution  (detail: `1-gear-resolution.md`)

```text
steps_per_deg     = (full_steps_per_rev × microsteps × G) / 360
resolution_deg    = 360 / (full_steps_per_rev × microsteps × G)   = 1 / steps_per_deg   (commanded)
fullstep_res_deg  = (360 / full_steps_per_rev) / G                 (REAL repeatable floor)
end_effector_arc  = reach_mm × resolution_deg × (π/180)            (mm of error at the gripper)
repeatability     ≈ fullstep_res_deg + backlash_deg
```

- `full_steps_per_rev` = 200 (1.8°) or 400 (0.9°) for the motor itself.
- **Microstepping buys *commanded* resolution + smoothness, NOT accuracy.** Real repeatable
  accuracy is bounded by the **full-step** angle through the reduction, then degraded by
  backlash. Per-microstep holding stiffness collapses as `T_inc ≈ T_hold · sin(90°/N)`
  (N microsteps/full-step: N=8 → 0.20, N=16 → 0.10) — so **do not** size load capacity against
  microsteps. (StepperOnline; FAULHABER.)
- Reduction choice: GT2 belt (`ratio = driven_teeth / motor_teeth`), planetary, **cycloidal**
  (the printable precision option — harmonic flexsplines can't be printed to tolerance),
  worm (self-locking → holds a base/shoulder pose unpowered, but low η + backlash).
- **Worked (NEMA17 200, 16μ, 5:1):** `steps_per_deg = 44.44`, commanded `0.0225°`, but real
  full-step floor `0.36°`. Doubling μ (16→32) halves the *commanded* number only; doubling the
  *ratio* (5→10) halves **both** → ratio, not microstepping, is how you buy real precision.

---

## [B] Torque & motor sizing  (detail: `2-torque-motor-sizing.md`)

> **The one rule:** size every joint at its **worst case = arm horizontal, fully extended,
> payload at full reach.**

```text
T_static_worst = g · Σ_i (m_i · d_i)            # g=9.81; m_i,d_i = mass & HORIZONTAL lever of every item DISTAL to the joint
I              ≈ Σ_i (m_i · d_i²)  (+ m·L²/3 per long slender link)
T_dyn          = I · α                          # α = target angular accel (rad/s²)
T_joint_req    = SF · (T_static_worst + T_dyn)  # SF = 1.5–2.0 (separate, exposed)
T_motor_req    = T_joint_req / (G · η)          # η: belt ~0.9, planetary ~0.7–0.8, worm low
I_reflected    = I_joint / G²                   # gearing tames inertia by G²
ADEQUATE  ⇔    T_hold · u ≥ T_motor_req         # u = usable fraction at the joint's RPM (~0.5; 0.6–0.7 slow joints)
```

- **Base yaw (vertical axis): gravity torque = 0** — sized by inertia/friction, not weight.
  **Shoulder is the whole-arm worst case;** wrists are light → big motors low, small motors high.
- Frame sizes: **NEMA17 ≈ 0.4–0.65 N·m**, **NEMA23 ≈ 1.2–3.0 N·m**. Escalate to NEMA23 the
  moment no sane `G` (one that still meets the joint **speed**) makes a NEMA17 satisfy the
  inequality.
- `u` (speed derate) and `SF` (design margin) are **different** and must stay separate; the
  authoritative `u` is the motor's torque–speed curve at the operating RPM.
- **Worked (generic shoulder):** `Σm·d=0.672` → `T_static≈6.59 N·m`; `I≈0.300`, `α=2` →
  `T_dyn≈0.60`; `SF=1.5` → `T_joint_req≈10.8 N·m`. At **50:1, η=0.8** → motor needs **0.27 N·m**
  → a 0.45 N·m NEMA17 clears it at `u≥0.6` (matches Annin **AR4**: NEMA17 + 50:1, 1 kg/600 mm).
  Drop to 20:1 for speed → 0.67 N·m → **forces NEMA23 + external driver.**

---

## [C] Speed, acceleration & step-rate  (detail: `3-speed-accel-steprate.md`)

```text
step_rate (steps/s) = joint_speed_deg_s × steps_per_deg         # → firmware max_sps
motor_rpm           = joint_speed_deg_s × G / 6                  # check vs motor torque–speed curve
α_max (rad/s²)      = T_available / I_joint                      # accel ceiling from spare torque
accel (steps/s²)    = α_max_deg_s2 × steps_per_deg               # → firmware accel
t_to_vmax           = v_max / accel ;  ramp_steps = v_max² / (2·accel)
```

- **The polled-stepping ceiling is the binding software limit.** The firmware runs **AccelStepper
  by polling `run()` in `loop()`** on an STM32F103 (72 MHz, **no FPU**). AccelStepper's documented
  ceiling is **~4,000 steps/s on a 16 MHz AVR**; on the F103 a single-instance position move tops
  out around **~14,000 steps/s** (derived by clock-scaling the no-FPU Arduino Due's *measured*
  16,214 sps; `runSpeed()` is higher, ~37 k). **The aggregate across 6 joints + serial telemetry
  in one `loop()` is meaningfully lower** — so **high microstepping × high joint speed can exceed
  the budget and lose steps.** ISR/integer-Bresenham steppers (Marlin ~10–40 kSps, grblHAL
  ~400 kSps, Klipper >100 k) are why printers go higher; PiBot stays polled for simplicity, so
  `max_sps` must respect this ceiling (default 1/16 μ keeps typical joint speeds feasible).
  **Bench-confirm the real aggregate ceiling under the 24 V PSU (task #5).**
- Coordinated motion: each joint's `dps = |target−current| / seconds` so the longest-travel joint
  paces the move — already implemented host-side in `move_synchronized` (`pibot/arm/manager.py`).
- **Worked (NEMA17, 16μ, 5:1, 60 deg/s):** `step_rate = 60 × 44.44 = 2,667 sps` (well under the
  ceiling; motor_rpm = 50); `accel = 26,667 steps/s²` → `t_to_vmax = 0.10 s`, ramp ≈ 3°.

---

## [D] Driver current, microstepping & power  (detail: `4-driver-current-power.md`)

```text
A4988   Vref ≈ 8 · I_peak · R_cs        (Pololu R_cs ≈ 0.068 Ω; clones often 0.1 Ω — MEASURE)
DRV8825 Vref = I_peak / 2               (R_cs = 0.1 Ω)
TMC2208/09  I_RMS ≈ 0.71 · Vref   or set run_current (RMS) in firmware/UART
set driver current to ≈ 0.7–0.9 × motor rated phase current   (RMS vs peak: distinguish!)
PSU:  I_supply ≳ Σ(rated_phase_current) × 1.2  + 30–50% margin  (transient/motion budget, NOT the hold-draw floor)
```

- **Onboard driver ceiling ≈ 2 A/phase** (A4988 ~1 A bare/2 A cooled; DRV8825 ~1.5/2.2; TMC2208/09
  ~1.2 A RMS). **NEMA17 fits onboard; a NEMA23 base (~2.8–3 A) MUST use an external TB6600/DM542**
  fed step/dir from a spare GPIO — a hardware ceiling, not a tuning issue.
- Microstepping: incremental torque `T·sin(90°/N)` falls with N, but pull-out torque + current stay
  ~constant → **smoothness, not torque/accuracy.** Default **1/16 + TMC interpolation**.
- **24 V > 12 V:** higher rail = faster winding current rise = more high-speed torque; 24 V is the
  arm/printer standard. Motors run warm — derate current ~0.8×.
- **PSU worked (6× NEMA17 @ 1.5 A, 24 V, HOLD):** steady hold draw ≈ 1.5 A total, but size to the
  *conservative* transient sum ≈ 9–11 A → the **Mean Well LRS-350-24 (14.6 A @ 24 V)** has the
  headroom (move it to LRS-450 if a NEMA23 base + external driver is added).

---

## The calculator — `pibot/arm/sizing.py` (the buildable deliverable)

Pure-stdlib (respects the `[ml]` boundary — no numpy; basic arithmetic only). Importable API +
`python -m pibot.arm.sizing <config.toml>` CLI. Robot-agnostic: everything below is config.

**Inputs (dataclasses / a TOML file):**

```text
MotorSpec   : frame, holding_torque_Nm, rated_current_A, rotor_inertia_kgm2, full_steps_per_rev
GearOption  : ratio G, efficiency η, type(belt|planetary|cycloidal|worm), backlash_deg
LinkSpec    : mass_kg, length_m, com_offset_m            # ordered base → tip
JointInput  : axis(vertical|horizontal), travel_deg(min,max), home_pos_deg,
              target_speed_deg_s, target_accel_rad_s2, microsteps,
              SF, u, gear_candidates[], motor_candidates[]
ArmSpec     : links[], payload_kg, reach_m, supply_voltage_V,
              onboard_current_limit_A (≈2.0), accelstepper_ceiling_sps (configurable, default ~12k)
```

**Per-joint algorithm (worst case = horizontal, fully extended):**
1. Distal mass table `{(m_i,d_i)}` = every link/motor/payload beyond the joint (each joint's
   table is a subset of the joint below it).
2. `T_static = g·Σ(m·d)` (zero for a vertical base axis); `I = Σ(m·d²) (+ mL²/3)`; `T_dyn = I·α`.
3. `T_joint_req = SF·(T_static+T_dyn)`.
4. For each `(G, motor)` candidate: `T_motor_req = T_joint_req/(G·η)`; **accept** if
   `T_hold·u ≥ T_motor_req` AND `motor_rpm = speed·G/6` is on the torque–speed curve AND
   `step_rate = speed·steps_per_deg ≤ ceiling`. Pick the **smallest G** that passes (max speed,
   min resolution waste); escalate NEMA17→NEMA23 if none pass.
5. Emit: `steps_per_deg`, `resolution_deg`, `fullstep_res_deg`, `end_effector_arc_mm`,
   `max_joint_speed`, `max_sps`, `accel_sps2`, `driver_current_A`, `needs_external_driver`,
   margin, and the **`JCFG[]` row** (`steps_per_deg, max_sps, accel` + the mechanical
   `min/max_deg, home_pos_deg` passed through from `JointInput`).

**Arm-level output:** per-joint table + total `psu_current_A` + which joints need external drivers
+ a copy-pasteable `JCFG[]` block for `firmware/pibot_arm_stm32/pibot_arm_stm32.ino`.

## Phased build order

1. **Spec (this doc + the 4 research refs).** Done — the authoritative reference.
2. **`pibot/arm/sizing.py` core:** the dataclasses + the four-domain formulas as small pure
   functions (`steps_per_deg`, `static_torque`, `dynamic_torque`, `reflect_to_motor`,
   `step_rate`, `vref_for_driver`, `psu_current`) + `size_joint()` / `size_arm()`.
3. **CLI + JCFG emitter + sample config** (`docs/` or `examples/` — the generic NEMA17 6-DOF of
   §[B] as `arm-generic-6dof.toml`), printing the per-joint report and the `JCFG[]` block.
4. **Tests** (`tests/test_arm_sizing.py`): assert the worked numbers from the research
   (`steps_per_deg=44.44`, shoulder `T_static≈6.59`, `T_joint_req≈10.8`, 50:1→`0.27 N·m`,
   `step_rate=2667`, A4988/DRV8825 Vref, PSU sum) — these are arithmetic-verified in the refs.
5. **(Optional)** expose as `pibot arm size <config>` CLI subcommand; link from `docs/runbooks/`.

## Definition of done

`bash scripts/check.sh` green (the calculator is pure-Python, typed, ≥80% covered); the generic
config reproduces every worked number in `docs/research/stepper-arm-sizing/`; the emitted `JCFG[]`
block compiles into `pibot_arm_stm32` unchanged. No hardware required to build or test this — it's
design-time tooling; the numbers it produces get **bench-validated** when the arm is built (task #5).

## Open inputs to supply when sizing a real arm (⬜)
1. Per-link masses + lengths + CG offsets (base→tip), payload, full reach.
2. Target per-joint speed + acceleration.
3. Motor catalog (holding torque, rated current, rotor inertia per frame you stock) + gear options
   (ratio, type, efficiency, backlash) + microstep setting.
4. Supply voltage + onboard driver current limit (board-specific — measure `R_cs`).

## References (full derivations + sources)
- `docs/research/stepper-arm-sizing/1-gear-resolution.md` — gear ratio, steps/deg, microstep≠accuracy.
- `docs/research/stepper-arm-sizing/2-torque-motor-sizing.md` — gravity/inertia torque, reflect-to-motor, NEMA sizing.
- `docs/research/stepper-arm-sizing/3-speed-accel-steprate.md` — step rate, AccelStepper/F103 ceiling, accel.
- `docs/research/stepper-arm-sizing/4-driver-current-power.md` — Vref/current, onboard-vs-external, PSU sizing.
- Ties into: `docs/plans/2026-06-13-pibot-arm-control.md` (the arm milestone) and
  `firmware/pibot_arm_stm32` `JCFG[]` (the consumer of the output).
