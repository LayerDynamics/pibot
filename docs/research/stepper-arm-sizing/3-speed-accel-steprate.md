# Speed, Acceleration & Step-Rate Limits for a DIY Stepper Robot Arm

**Scope.** A robot-agnostic, formula-complete reference for sizing the *motion* envelope of a
DIY stepper robot arm: how a desired **joint speed (deg/s)** turns into a **step rate
(steps/s)**, why the **motor torque-speed curve** caps that rate, why the **firmware's polling
loop** caps it again (often *lower* than the motor would), how **acceleration** is bounded by
torque-vs-inertia, and how a multi-joint move is **coordinated in time**. It feeds a generic
NEMA17 6-DOF sizing calculator and the per-joint `max_sps` / `accel` config.

**Firmware context that pins the numbers.** PiBot's arm firmware
(`firmware/pibot_arm_stm32/pibot_arm_stm32.ino`) runs the Arduino **AccelStepper** library on an
**STM32F103 (Cortex-M3, 72 MHz, no FPU)**. It drives each joint by **polling** —
`steppers[j].run()` (position moves, with accel) or `steppers[j].runSpeed()` (velocity jog,
constant speed) — once per pass of the main `loop()`, while it also services serial telemetry.
Each joint has a tunable `max_sps` (steps/s) and `accel` (steps/s²). This polling architecture,
not the motor, is usually the binding constraint, and that fact drives every recommendation below.

> Notation used throughout: `θ̇` = joint angular speed (deg/s); `G` = gear ratio (motor turns per
> output turn, dimensionless); `fullsteps` = motor full steps per rev (200 for a 1.8° NEMA17);
> `μ` = microstep factor (1, 2, 4, 8, 16, 32…); `steps_per_deg` = step rate scale; `f` = step rate
> (steps/s); `a` = acceleration (steps/s²); `v_max` = top step rate (steps/s); `T` = torque (N·m);
> `I` = reflected inertia at the joint (kg·m²); `α` = angular acceleration (rad/s² or deg/s²).

---

## 1. Joint speed → step rate (the `max_sps` driver)

The conversion from a human-facing joint speed to the firmware's step rate is purely geometric.

**Steps per degree of *output* (joint) rotation:**

```
steps_per_deg = (fullsteps × μ × G) / 360        [steps / deg]
```

- `fullsteps × μ` = microsteps per motor revolution
- `× G` because the joint turns `G`× slower than the motor (gear reduction multiplies resolution)
- `/ 360` converts per-rev to per-degree

**Joint speed → step rate** (this is the number you put in firmware as `max_sps`):

```
f (steps/s) = θ̇ (deg/s) × steps_per_deg
            = θ̇ × (fullsteps × μ × G) / 360
```

**Cross-checks at the motor shaft** (useful for reading torque-speed curves, which are plotted in
RPM or rev/s, *not* in joint deg/s):

```
motor_rpm     = θ̇ (deg/s) × G / 6          (since 360 deg/min-per-rpm ÷ 60 s/min = 6 deg/s per rpm)
motor_rev_s   = motor_rpm / 60 = θ̇ × G / 360
f (steps/s)   = motor_rev_s × fullsteps × μ   (identical to the formula above — sanity check)
```

The `θ̇ × G / 6` form is the quick deg/s ↔ RPM bridge: **1 rpm at the motor = 6 deg/s of motor
shaft = `6/G` deg/s at the joint.** Always evaluate the torque-speed curve at `motor_rpm`, because
gearing means a slow, high-resolution joint can still be spinning the motor fast.

---

## 2. The stepper torque-speed curve (the *physical* speed ceiling)

A stepper does **not** make constant torque. Holding torque is the datasheet headline, but the
**dynamic / pull-out torque** — the max load torque it can carry at a given speed *without losing
sync (skipping steps)* — falls as speed rises. The usable maximum speed is the point where the
available pull-out torque drops below the load's demand (gravity + friction + the acceleration
term from §4). Past that the motor stalls and silently drops steps — catastrophic for an arm,
which has no closed-loop position feedback in this architecture.

Why the curve droops: each winding is an inductor (`L`). To make torque you must drive current `i`
into it, and `V = L·di/dt` means current rises at a *finite* rate. As step frequency climbs, each
phase gets less time before it must reverse, so current never reaches its rated value and torque
collapses. (Portescap, Servotecnica, FAULHABER AN002 all describe this as the inductance-limited
roll-off.)

**Supply voltage is the main lever.** A higher drive voltage forces current to rise faster
(`di/dt = V/L`), so the windings hit rated current even at high step frequency — **the whole
torque-speed curve shifts up and to the right.** This is exactly what a modern **chopper / constant-
current driver** (A4988, DRV8825, TMC2208/2209, the kind on the 4.2.2 boards PiBot uses) does: it
runs from a bus voltage *several times* the motor's nominal rating and PWM-chops to hold current at
the set limit. Common guidance: pick a driver bus **2–5× the motor's nominal voltage** (chopper
designs go up to ~8–20× for industrial NEMA setups). The practical consequence for sizing: *the
24 V bus, not the 12 V one, is what makes the higher `max_sps` values below actually reachable*
without stall. (Caveat from the sources: excessive bus voltage can cause current-regulation ripple
and a slight torque dip at low/medium speed — there is a sweet spot, not "more is always better.")

**Takeaway for sizing:** read the chosen motor+driver+voltage torque-speed curve, find the
`motor_rpm` where pull-out torque still exceeds your worst-case joint load **with margin** (≥50% is
typical), convert that RPM to deg/s and then to steps/s via §1 — that is the *motor's* speed ceiling.
Then compare it to the *firmware's* ceiling in §3 and **take the lower of the two.** For a geared
DIY arm with a chopper driver on 24 V, the firmware ceiling (§3) is very often the binding one.

---

## 3. The AccelStepper / MCU polling ceiling (the *binding* limit for PiBot)

This is the section that actually sets `max_sps`, and the number it produces is usually **lower**
than §2's motor ceiling. AccelStepper is a **software, polled** stepper: there is no timer
interrupt generating pulses. Every call to `run()`/`runSpeed()` emits **at most one step**, and
only if one is due based on elapsed time — so *the loop must call `run()` at least once per step
interval, for every joint, or steps are simply late and the motion stutters / loses sync.*

**Documented AVR ceiling.** The AccelStepper author states:

> *"The fastest motor speed that can be reliably supported is about 4000 steps per second at a
> clock frequency of 16 MHz on Arduino such as Uno etc."*

The cause is explicitly compute, not the motor: AccelStepper runs the **David Austin** real-time
ramp algorithm (`"speed calculations as described in 'Generate stepper-motor speed profiles in real
time' by David Austin"`) which does **floating-point** work (a `sqrt`, several multiplies/divides)
*per step* inside `run()`. On an 8-bit 16 MHz AVR that math is the bottleneck — hence ~4 kHz.

**Why the F103 is faster but still bounded — and the load-bearing number.** Naive clock-scaling
(`4000 × 72/16 = 18 kHz`) **overstates** the F103 because the Cortex-M3 (like the AVR) **has no
hardware FPU** — float ops are *software-emulated*, which is expensive on M3. (PiBot's own build map
confirms this: the linked `AccelStepper.cpp.o` pulls in `__aeabi_dmul`, `__aeabi_dsub`,
`__aeabi_ddiv`, `__aeabi_d2iz` and `sqrt` — the ARM EABI **software double-precision** routines that
exist precisely *because* there is no FPU.)

The right anchor is a **measured** number on the closest architectural twin. The **Arduino Due**
(SAM3X8E) is **Cortex-M3, no FPU, 84 MHz** — essentially the F103's bigger sibling. AccelStepper's
own docs report a measured Due result:

> *"Gregor Christandl reports that with an Arduino Due and a simple test program, he measured
> 43163 steps per second using `runSpeed()`, and 16214 steps per second using `run()`."*

Note the **2.6× gap** between `runSpeed()` (constant speed, *no* per-step float ramp) and `run()`
(full David Austin float ramp) on the *same* chip — direct evidence that the float math, not the
GPIO, is the ceiling.

> **Derived F103 single-instance estimate (NOT a measurement — flagged per no-fabrication rule):**
> scaling the Due's measured `run()` figure by clock,
> `16,214 × (72/84) ≈ ~14,000 steps/s` for a **single** AccelStepper instance running
> position moves on the F103. The `runSpeed()` (jog) path scales similarly to `~37,000 steps/s`.
> These are first-order estimates from the Due anchor; treat ~14 kSps as the **optimistic
> single-joint** ceiling, to be bench-confirmed (PiBot task #5).

**Apportion DOWN for a real arm.** The ~14 k figure is for *one* joint with an otherwise empty
loop. PiBot's loop polls **up to 4 joints per board** *and* drains/sends serial telemetry every
pass. Each joint's `run()` must still be reached once per its own step interval, so the **aggregate
step rate across all polled joints + serial overhead** is the honest cap — not 14 k per joint. As a
planning rule, keep the *sum* of simultaneous step rates comfortably under the single-instance
ceiling (a conservative working budget is a few thousand sps per joint for 3–4 joints sharing one
loop, pending bench measurement). The coordinated-move structure in §5 helps here: in a synchronized
move only the longest-travel joint runs near its peak; the rest are scaled down, so the *aggregate*
is well below `N × max_sps`.

**Why ISR/timer steppers (Marlin, grblHAL, Klipper) go far higher — and why PiBot isn't one.**
These move the pulse generation into a **timer interrupt** using **integer Bresenham** stepping (no
per-step float), so they hit rates a polled float loop never can:

| Firmware / arch                         | Step-rate ceiling        | Mechanism |
|-----------------------------------------|--------------------------|-----------|
| AccelStepper, 16 MHz AVR (Uno)          | **~4,000 sps**           | polled, software float ramp |
| AccelStepper `run()`, Cortex-M3 no-FPU (Due, measured) | **~16,200 sps** | polled, software float ramp |
| AccelStepper, F103 72 MHz (derived est.)| **~14,000 sps** single inst. | polled, software-emulated double |
| 8-bit Marlin (timer ISR)                | **~10,000–40,000 sps**   | ISR, integer Bresenham, multi-stepping |
| grblHAL (32-bit ARM, timer ISR)         | **~400,000 sps**         | ISR on faster ARM (8-bit Grbl ≈ 30 kSps) |
| Klipper, 8-bit MCU                       | **>100,000 sps**         | host computes step train, MCU replays compressed steps |
| Klipper, 32-bit MCU                      | **>600,000 sps**         | same, on faster MCU |

Klipper is the closest analog to PiBot's *system* shape (host = Pi computes timing, MCU = STM32 just
executes) — but PiBot deliberately uses the simpler **polled AccelStepper** on the MCU, so it lives
in the ~14 k single-instance / few-k-per-joint regime, **not** the 100 k+ ISR regime.

**The microstepping tradeoff this forces.** Step rate scales *linearly* with microstep factor `μ`
(§1). High `μ` gives smoothness and resolution but multiplies `f` — and the polled ceiling is fixed,
so **high `μ` × high joint speed can blow past the ceiling.** The microstep setting is therefore not
a free "more is better" knob: it must be chosen so that
`θ̇_max × (fullsteps × μ × G)/360` stays under the §3 ceiling *for the aggregate of all joints
running at once.* (See the worked example in §6 for exactly how this bites.) In short: **gear
reduction buys you resolution cheaply (it's free step-rate headroom per degree); microstepping buys
resolution by spending the scarce step-rate budget.**

---

## 4. Acceleration (the `accel` driver)

AccelStepper uses a **constant-acceleration (trapezoidal) velocity profile** via the David Austin
algorithm: speed ramps **linearly** up to `max_sps`, cruises, then ramps linearly down. The single
tunable is `setAcceleration(a)` in **steps/s²** (PiBot's per-joint `accel`).

**Time and distance to reach top speed** (classic constant-accel kinematics, in step units):

```
t_to_vmax  = v_max / a                 [s]      (v_max = max_sps, a = accel)
steps_ramp = v_max² / (2 a)            [steps]  (steps consumed in one ramp)
```

If the total move is shorter than `2 × steps_ramp`, the profile is **triangular** (never reaches
`max_sps`): peak speed `v_peak = sqrt(a × total_steps)` and the move time is `2 × v_peak / a`.

**Acceleration is bounded by torque vs inertia**, not chosen freely. Newton's second law for
rotation sets the hard limit:

```
α_max (rad/s²) = T_available / I_joint
```

- `T_available` = pull-out torque at the *current* speed (from §2) **minus** the static load
  (gravity holding torque + friction) — only the *surplus* torque accelerates the joint.
- `I_joint` = total inertia reflected to the joint: link/payload inertia about the joint axis +
  motor rotor inertia × `G²` (gearing multiplies reflected rotor inertia by the square of the ratio).

Convert `α_max` (rad/s² at the joint) to the firmware's steps/s²:

```
a_max (steps/s²) = α_max (rad/s²) × (180/π) (deg/rad) × steps_per_deg
```

So `accel` must satisfy `a ≤ a_max`. Set it too high and the demanded torque
(`T = I_joint × α`) exceeds what the motor makes at that speed → **stall and lost steps**, the same
failure mode as overspeed. In practice you start conservative, then raise `accel` on the bench until
just below the speed/jerk where the joint skips, and keep margin.

**S-curve / jerk (brief).** Trapezoidal profiles have a *step discontinuity in acceleration* at the
ramp corners (infinite jerk), which excites mechanical ringing in a flexible arm. S-curve profiles
round those corners by limiting jerk (`d³θ/dt³`) for smoother, lower-vibration motion. AccelStepper
does **not** implement S-curve (it is strictly trapezoidal) — mentioned only for completeness; if
jerk-limiting is ever needed it must be done host-side or with a different stepper engine.

---

## 5. Coordinated multi-joint timing (`move_synchronized`)

For an arm, joints must **arrive together**, or the end-effector traces a wrong, jerky path. The
standard technique: pick a single move duration, then **scale every joint's speed to its own travel
distance** so they all finish at once. The joint with the farthest to go (relative to its speed
limit) sets the pace; everyone else moves *slower* to match.

PiBot implements exactly this host-side in `pibot/arm/manager.py::ArmManager.move_synchronized`:

```python
dps = abs(target - current) / seconds      # per joint
self.jmove(joint, target, dps)             # send each joint its scaled speed
```

Each joint gets `dps = |Δθ_joint| / seconds`. Because every joint divides its *own* travel by the
*same* `seconds`, the longest-travel joint demands the highest `dps` and the rest are proportionally
slower — synchronized arrival. The firmware (`jmove` in the sketch, line ~144) then **clamps each
joint's requested speed to that joint's `max_sps`**; if `seconds` is too small for some joint's
travel, that joint saturates at `max_sps` and *lags* (sync breaks). The operator's job is to choose
`seconds` large enough that the busiest joint's required `dps` stays at or below its `max_sps`:

```
seconds_min = max over joints of ( |Δθ_joint| × steps_per_deg_joint / max_sps_joint )
```

Pick `seconds ≥ seconds_min` for guaranteed synchrony. This is also what keeps the §3 **aggregate**
step rate in check: in a coordinated move the slowest-arriving (longest-travel) joint runs near its
peak while the others are scaled *down*, so the total simultaneous step rate is meaningfully below
`N × max_sps` — the loop has headroom it wouldn't have if every joint ran flat-out independently.

---

## 6. Worked generic example (NEMA17, 16 microsteps, 5:1, want 60 deg/s)

Inputs: `fullsteps = 200` (1.8° NEMA17), `μ = 16`, `G = 5`, target `θ̇ = 60 deg/s`.

**Step resolution:**

```
steps_per_deg = (200 × 16 × 5) / 360 = 16000 / 360 = 44.44 steps/deg
```

**Step rate at 60 deg/s (the candidate `max_sps`):**

```
f = 60 × 44.44 = 2,666.7 steps/s  ≈ 2,667 sps
```

**Motor speed cross-check (read the torque curve here):**

```
motor_rpm   = 60 × 5 / 6 = 50 rpm
motor_rev_s = 50/60 = 0.833 rev/s
f check     = 0.833 × 200 × 16 = 2,667 sps   ✓ (matches)
```

50 rpm is well within the flat, high-torque region of any NEMA17 torque-speed curve on a 24 V
chopper driver — **the motor is not the limit here.**

**Check against the §3 polled ceiling:** 2,667 sps is comfortably under the ~14 k single-instance
F103 estimate — feasible for *one* joint at `μ=16`. But watch the **aggregate**: 6 joints each near
2.7 kSps would demand ~16 kSps total through one polled loop *plus* telemetry, which **exceeds** the
single-instance ceiling. Two mitigations: (a) coordinated moves (§5) mean they rarely all peak at
once; (b) split across boards (PiBot's 3+3 across two boards halves the per-loop burden). If you
truly needed all six at full speed simultaneously, you'd have to drop `μ` to **8**
(`steps_per_deg = 22.22`, `f = 1,333 sps`, aggregate ~8 kSps) to stay feasible — the concrete
microstep-vs-speed tradeoff from §3.

**A representative microstep ladder at 60 deg/s, 5:1** (shows the polled budget directly):

| μ  | steps_per_deg | f @ 60 deg/s | single-joint vs ~14k | 6-joint aggregate |
|----|---------------|--------------|----------------------|-------------------|
| 8  | 22.22         | 1,333 sps    | fine                 | ~8,000 sps — fits |
| 16 | 44.44         | 2,667 sps    | fine                 | ~16,000 sps — over single-inst.; rely on §5/board split |
| 32 | 88.89         | 5,333 sps    | fine alone           | ~32,000 sps — not feasible polled |

**Acceleration and time-to-speed.** Suppose the bench-determined torque surplus gives
`α_max ≈ 600 deg/s²` at this load (illustrative — derive yours from `T_available / I_joint` in §4).
Convert to step units at `μ=16`:

```
a = 600 deg/s² × 44.44 steps/deg = 26,667 steps/s²   → set firmware accel ≈ 26,000 (with margin)
```

Time and distance to reach the 2,667 sps top speed:

```
t_to_vmax  = v_max / a = 2,667 / 26,667 = 0.10 s
steps_ramp = v_max² / (2a) = 2,667² / (2×26,667) = 133 steps  ( = 133/44.44 ≈ 3.0 deg per ramp)
```

So this joint reaches full speed in ~0.1 s over ~3° — meaning any move shorter than ~6° is
**triangular** (never cruises at 60 deg/s). That's the check that decides whether `max_sps` is even
relevant for short jogs.

**Resulting firmware config for this joint** (`JCFG` row in `pibot_arm_stm32.ino`):

```
s/deg = 44.44      max_sps = 2667 (μ=16, single-joint) or 1333 (μ=8, 6-joint headroom)
accel = 26000      ← from α_max × steps_per_deg, with margin; bench-tune downward if it skips
```

The chosen `μ` must be the same one set on the driver's MS pins, and the final `max_sps`/`accel`
must be **confirmed on the bench under the 24 V PSU** (PiBot task #5) — the numbers above are the
*starting* envelope, not a substitute for measuring where the specific motor+load actually stalls.

---

## Summary cheat-sheet

```
steps_per_deg = fullsteps × μ × G / 360
max_sps       = θ̇_max × steps_per_deg            (also = motor_rpm/60 × fullsteps × μ)
motor_rpm     = θ̇ × G / 6
ceiling       = min( motor torque-speed limit (§2),  polled MCU limit (§3 ≈ 14k single-inst, less aggregate) )
accel         = α_max × steps_per_deg,  α_max = T_surplus / I_joint
t_to_vmax     = max_sps / accel
seconds_sync  = max_j( |Δθ_j| × steps_per_deg_j / max_sps_j )
```

**Single load-bearing number:** on PiBot's STM32F103 (Cortex-M3, *no FPU*, 72 MHz) running polled
AccelStepper with the David Austin float ramp, the realistic **single-instance** position-move
ceiling is **~14,000 steps/s (derived from the measured 16,214 sps on the architecturally-identical
no-FPU Cortex-M3 Arduino Due, clock-scaled 72/84)** — and the *aggregate* across several joints +
serial telemetry in one `loop()` is meaningfully lower. This, not the motor, is what caps `max_sps`
and bounds the microstepping choice. Confirm on the bench (task #5).

---

## Sources

- **AccelStepper Class Reference (airspayce / Mike McCauley)** — primary doc for the ~4000 sps @
  16 MHz limit; measured Due figures (43163 sps `runSpeed()` / 16214 sps `run()`); method units
  (`setMaxSpeed`, `setAcceleration` in steps/s and steps/s²); "`run()` must be called frequently
  enough." <https://www.airspayce.com/mikem/arduino/AccelStepper/classAccelStepper.html>
- **AccelStepper library home page** — confirms the **David Austin** "Generate stepper-motor speed
  profiles in real time" algorithm, "max stepping speed to about 4kHz", multiple-simultaneous-
  stepper support, non-blocking API. <https://www.airspayce.com/mikem/arduino/AccelStepper/>
- **David Austin, "Generate stepper-motor speed profiles in real time"** (Embedded Systems
  Programming, Jan 2005) — the constant-acceleration (trapezoidal) ramp math AccelStepper implements;
  fixed-point, no tables. PDF mirror:
  <https://www.boost.org/doc/libs/1_85_0/libs/safe_numerics/example/stepper-motor.pdf>
- **Portescap — Torque-Speed Curve Generation in Stepper Motors** — pull-out torque, inductance-
  limited roll-off, driver/voltage dependence of the curve.
  <https://www.portescap.com/en/newsroom/blog/2022/12/torque-speed-curve-generation-in-stepper-motors>
- **Servotecnica — Stepper motors: is high torque at high speeds possible?** — higher supply voltage
  raises the torque/speed curve (di/dt = V/L); chopper drives run several× nominal voltage; 2–5×
  recommendation and the over-voltage ripple caveat.
  <https://servotecnica.com/en/stepper-motors-is-high-torque-at-high-speeds-possible/>
- **FAULHABER AN002 — Reading and understanding a torque curve (PDF)** — pull-in/pull-out torque
  definitions; curves are driver-specific.
  <https://www.faulhaber.com/fileadmin/Import/Media/AN002_EN.pdf>
- **PBC Linear — How to Maximize Stepper Motor Speed** — voltage/inductance limits on top speed.
  <https://pbclinear.com/blogs/blog/operating-stepper-motors-at-high-speeds>
- **The Grbl Project — "How fast can it go?"** + **grblHAL** — 8-bit Grbl ≈ 30 kSps, grblHAL on ARM
  ≈ 400 kSps via timer ISR. <https://www.grbl.org/single-post/how-fast-can-it-go>
- **Marlin stepper ISR timing (softsolder) / RepRap Step rates** — Marlin timer-ISR step rate
  ~10–40 kSps with single/double/multi-stepping. <https://softsolder.com/2013/06/04/marlin-firmware-stepper-interrupt-timing/>
  · <https://reprap.org/wiki/Step_rates>
- **Klipper FAQ (Klipper3d/klipper)** — host computes a compressed step train, MCU replays it;
  8-bit Marlin ≈ 10 kSps vs 8-bit Klipper >100 kSps; 32-bit Klipper >600 kSps. Closest analog to
  PiBot's Pi-host + STM32-MCU split. <https://github.com/Klipper3d/klipper/blob/master/docs/FAQ.md>
- **Arduino Due / SAM3X8E (Arduino docs + forum)** — confirms Cortex-M3, 84 MHz, **no FPU**;
  software float is expensive on M3 (basis for using the Due as the F103 proxy and for the
  no-FPU mechanism). <https://docs.arduino.cc/hardware/due> ·
  <https://forum.arduino.cc/t/alternative-to-floating-point-computation-for-cortex-m3/403623>
- **PiBot codebase (verified in-repo, not external):**
  `firmware/pibot_arm_stm32/pibot_arm_stm32.ino` (AccelStepper on GenF1; per-joint `max_sps`/`accel`;
  polled `run()`/`runSpeed()`; build map shows `__aeabi_dmul/_dsub/_ddiv` + `sqrt` software-float
  symbols → no FPU) and `pibot/arm/manager.py::ArmManager.move_synchronized`
  (`dps = |target-current| / seconds`, longest-travel joint sets the pace, firmware clamps to
  `max_sps`).

### Uncertainties / things to bench-confirm (per the no-fabrication rule)
- **~14,000 sps F103 single-instance figure is a *derived estimate*** (Due 16214 × 72/84), **not a
  measurement**. The real F103 number depends on compiler/STM32duino core float performance and the
  exact loop body; measure it (task #5).
- **Per-joint aggregate budget** (a few kSps × N joints + serial) is a planning rule, not a measured
  bound — confirm by scoping actual step pulses with all joints + telemetry active.
- **`α_max`, `T_surplus`, `I_joint`** in §4/§6 are illustrative; derive the real values from the
  chosen motor's pull-out curve and the arm's measured/CAD inertia, then bench-tune `accel` down to
  a no-skip margin.
