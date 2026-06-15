# Gear Ratio & Angular Resolution — Stepper-Motor Robot Arm (Reference)

Authoritative, formula-complete reference for sizing the drivetrain of a generic
NEMA17-based, 6-DOF stepper robot arm. This feeds a **robot-agnostic, configurable**
engineering spec and a Python sizing calculator. Every formula defines its variables and
units; the worked example shows how the numbers move when you change microstepping or
reduction.

> **The one idea that governs this whole document:** microstepping multiplies the
> *commanded resolution* but does **not** multiply *real, repeatable accuracy*. Real
> accuracy is bounded by the **full-step** angle through the reduction, then further
> degraded by **backlash**. Keep these two numbers — commanded resolution and full-step
> accuracy — side by side at all times.

---

## 1. The steps-per-degree chain

### 1.1 The core identity

```text
steps_per_deg = (full_steps_per_rev × microsteps × gear_ratio) / 360
```

Equivalently, per full revolution of the **output (joint)**:

```text
steps_per_rev_output = full_steps_per_rev × microsteps × gear_ratio
steps_per_deg        = steps_per_rev_output / 360
```

**Variable glossary (units):**

| Symbol               | Meaning                                                            | Units                     |
| -------------------- | ----------------------------------------------------------------- | ------------------------- |
| `full_steps_per_rev` | Motor full steps per *motor-shaft* revolution                     | steps / motor-rev         |
| `microsteps`         | Microstep subdivision set in the driver (1, 2, 4, 8, 16, 32, 256) | microsteps / full step    |
| `gear_ratio`         | Reduction from motor shaft to joint output (driven : motor)       | dimensionless (e.g. 5)    |
| `steps_per_deg`      | Driver pulses per degree of **joint** rotation                    | microsteps / output-degree|
| `360`                | Degrees per revolution                                            | deg / rev                 |

`full_steps_per_rev` for the common NEMA17 hybrid steppers:

- **1.8° motor** → `360 / 1.8 = 200` full steps/rev (the default — most NEMA17s).
- **0.9° motor** → `360 / 0.9 = 400` full steps/rev (finer; half the step angle).

This is the same identity 3D-printer firmware uses. Klipper's `rotation_distance`
machinery is the canonical statement of it: `full_steps_per_rotation` defaults to 200
(set 400 for a 0.9° motor), `microsteps` is "most commonly 16", and `gear_ratio` is the
gearbox reduction. (Klipper — *Rotation Distance*, see Sources.)

### 1.2 Rearrangements (solve for any unknown)

Given a target `steps_per_deg` (e.g. a firmware field you must fill), solve for whichever
quantity is free:

```text
gear_ratio   = (steps_per_deg × 360) / (full_steps_per_rev × microsteps)
microsteps   = (steps_per_deg × 360) / (full_steps_per_rev × gear_ratio)
full_steps_per_rev = (steps_per_deg × 360) / (microsteps × gear_ratio)
```

> **Practical note:** `microsteps` and `full_steps_per_rev` are not free design knobs in
> the field — they are fixed by the driver setting and the motor you bought. The only
> knob you choose mechanically is `gear_ratio`. So in practice the first rearrangement
> (solve for `gear_ratio`) is the design equation, and the calculator should treat
> `gear_ratio` as the dependent variable when given a target resolution.

### 1.3 gear_ratio direction convention (read this twice)

`gear_ratio` here is **driven : motor** = (output revolutions denominator). A 5:1
**reduction** means the motor turns 5× for every 1 output turn, which *increases* both
torque and resolution at the joint.

Following Klipper's convention: *"if a stepper with a 16-toothed pulley drives the next
pulley with 80 teeth then one would use `gear_ratio: 80:16`."* That ratio `80/16 = 5`
is a **5:1 reduction**. So in every formula above, `gear_ratio = driven_teeth /
motor_teeth = 80/16 = 5`. If you ever find yourself *multiplying* the joint speed by the
ratio, you have it upside down — reduction makes the joint **slower** and **finer**, never
faster.

---

## 2. Angular resolution and accuracy at the gripper

### 2.1 Commanded angular resolution

```text
resolution_deg = 360 / (full_steps_per_rev × microsteps × gear_ratio)
               = 1 / steps_per_deg
```

This is the smallest angular increment the firmware can **command** at the joint. It is
the reciprocal of `steps_per_deg`.

### 2.2 Resolution → arc length at the end effector

Joint angular error maps to a linear error at the gripper through the arm reach. Convert
degrees to radians first:

```text
radians         = resolution_deg × (π / 180)
arc_length_mm   = R × radians = R × resolution_deg × (π / 180)
```

**Variables:**

| Symbol          | Meaning                                                   | Units    |
| --------------- | -------------------------------------------------------- | -------- |
| `R`             | Distance from the joint axis to the gripper (reach)      | mm       |
| `resolution_deg`| Per-step joint angle from §2.1                           | deg      |
| `arc_length_mm` | Linear displacement at the gripper for one joint step    | mm       |

Errors **stack** down the kinematic chain: the base joint has the longest moment arm to
the gripper, so its angular error dominates the end-effector error budget — which is
exactly why the base/shoulder get the highest reduction (see §3.4). A real-world anchor:
on the popular AR2/AR3-class arm, a single **1.8° full step** at one joint produces on the
order of **~4.3 mm** of motion at the end effector — a direct demonstration of
`arc = R × radians` (1.8° ≈ 0.0314 rad ⇒ R ≈ 137 mm of effective arm at that joint).
(Wevolver AR2 spec; arXiv pick-and-place arm — see Sources.)

### 2.3 When is resolution "good enough"?

There is **no universal sourced threshold** — "good enough" is a budget derived from your
own reach and tolerance. The design rule of thumb used for small desktop arms is to keep
per-joint **commanded** resolution in the **0.05°–0.1°** range, and tighter (≤ 0.02°) on
the base/shoulder where `R` is largest. Derive the real target from the arc-length budget:

```text
resolution_deg_max = (tolerance_mm / R) × (180 / π)
```

e.g. for a 0.5 mm gripper tolerance at R = 400 mm: `(0.5/400) × 57.2958 ≈ 0.072°`. Treat
0.05–0.1° as a *starting* heuristic, not a spec — always reconcile it against
`tolerance_mm / R`.

> **Accuracy ≠ resolution.** §2.1 gives the *commanded* resolution. The **repeatable
> accuracy** the joint can actually hold is bounded by the **full-step** angle through the
> reduction (microstepping aside — see §5) and then *reduced* by backlash (§4):
>
> ```text
> resolution_fullstep_deg = 360 / (full_steps_per_rev × gear_ratio)   # microsteps = 1
> ```

---

## 3. Reduction mechanisms for arm joints

You almost never drive an arm joint directly from a NEMA17 — the un-geared 1.8° step
(0.36°/step even at the joint with no reduction) is far too coarse and the motor's ~0.4 N·m
holding torque too weak. You add a reduction stage. The choice trades **backlash,
efficiency (η), backdrivability, stiffness, cost, and 3D-printability**.

### 3.1 Mechanism comparison

| Mechanism                   | Typical single-stage ratio | Backlash            | Efficiency η | Backdrivable?        | 3D-printable?            | Cost    | Notes |
| --------------------------- | -------------------------- | ------------------- | ------------ | -------------------- | ------------------------ | ------- | ----- |
| **GT2 belt + pulleys**      | 2:1 – 6:1 (per stage)      | Low (belt stretch)  | High (~0.95) | Yes                  | Pulleys yes; needs belt  | $       | Quiet, compliant; ratio = driven_teeth/motor_teeth |
| **Planetary gearbox**       | 3:1 – 10:1 (per stage)     | Moderate–high       | High (~0.9)  | Yes                  | Printable but backlash-prone | $–$$ | Off-the-shelf NEMA17 planetaries common (e.g. 5.18:1) |
| **Cycloidal drive**         | 10:1 – 50:1 (single stage) | Low (near-zero)     | Moderate     | Low (often no)       | **Yes — DIY favorite**   | $$      | High ratio + low backlash in one printable stage |
| **Harmonic / strain-wave**  | 30:1 – 160:1 (single stage)| **Zero**            | Low–moderate | No                   | **Hard** (tight tolerance, flexspline) | $$$ | Best precision; impractical to print well |
| **Worm gear**               | 20:1 – 100:1 (single stage)| Moderate (tunable)  | Low (~0.4–0.7)| **No — self-locking**| Possible, friction-heavy | $$      | Holds joint angle with **zero power**; great for base/shoulder |

### 3.2 Belt (GT2) — the simplest reduction

For belt/pulley stages the ratio is exact and countable:

```text
gear_ratio = driven_pulley_teeth / motor_pulley_teeth
```

(16T → 80T = 5:1.) Pros: cheap, quiet, high η, compliant (absorbs shock), fully
specifiable from tooth counts. Cons: limited single-stage ratio (~6:1 before the small
pulley gets too few teeth), belt stretch adds compliance/backlash under load.

### 3.3 Cycloidal vs. harmonic (the precision pair)

Both give **high ratio in a single stage with low/zero backlash** — the property arm
joints want. The split for a DIY build:

- **Harmonic / strain-wave:** *zero* backlash, very high single-stage ratio, but **low
  stiffness and poor efficiency**, and it "requires incredibly high machining tolerances
  and is very expensive" — the flexspline is impractical to 3D-print well.
- **Cycloidal:** near-zero backlash and high ratio, and — critically — **"quite a few
  people have successfully designed their own cycloid gearing"** on a 3D printer, whereas
  "harmonic gearing is a lot harder to manufacture." This is why nearly every printed arm
  (Triple-Cycloidal arm, the 132:1 hypocycloid NEMA17 gearbox, etc.) uses cycloidal, not
  harmonic. (Eureka/PatSnap; Hackaday cycloidal arm; Thingiverse 371422 — see Sources.)

Conventional **planetary** gears win on efficiency, torque density, and stiffness but are
"rarely utilized in high-precision scenarios due to backlash issues" — fine for a
mid-stage or a forearm, marginal for a base.

### 3.4 Picking a ratio per joint

Higher reduction = finer resolution + more torque, but slower joint and (for most
mechanisms) lower efficiency / no backdrivability. The convention for a 6-DOF arm:

| Joint group           | Why                                                        | Typical reduction        |
| --------------------- | --------------------------------------------------------- | ------------------------ |
| **Base / J1, shoulder / J2** | Longest moment arm to gripper (largest `R`) + carries the whole arm's weight → needs the most torque *and* finest resolution | **High: 20:1 – 50:1** (cycloidal/harmonic; worm if hold-without-power matters) |
| **Elbow / J3**        | Moderate load and reach                                   | **Medium: 15:1 – 30:1**  |
| **Wrist / J4–J6**     | Light, fast, small `R`                                    | **Low: 5:1 – 20:1** (belt or small planetary OK) |

DIY cycloidal arms cluster in the **20:1–50:1** band, with **27:1–30:1** common for
intermediate joints and 48:1–50:1 for high-torque base/shoulder (the AR4 uses 50:1 geared
NEMA17s). (Hackaday Triple-Cycloidal; AR4 50:1 — see Sources.)

---

## 4. Backlash and repeatability

**Backlash** is the lost motion ("dead zone") when a joint reverses direction: the motor
turns but the output does not, until the gear teeth re-contact on the other flank. It is
the dominant limit on **repeatability** for a printed arm — usually far larger than the
commanded resolution, so refining `microsteps` is pointless if backlash swamps it.

- **Why cycloidal/harmonic beat printed spur/planetary:** strain-wave drives are
  *zero-backlash* by construction (continuous tooth engagement of the flexspline), and
  cycloidal drives engage many lobes simultaneously, giving *near-zero* backlash. Printed
  spur/planetary trains accumulate backlash at every mesh and from print tolerance, so
  reversal error stacks.
- **Effect on repeatability:** any reversal error directly enters the position budget. A
  joint with 0.0225° commanded resolution but 0.5° of backlash repeats to ~0.5°, not
  0.0225°. Budget backlash as its own term: `repeatability ≈ resolution + backlash`.

### 4.1 Anti-backlash techniques (representative — not exhaustive)

| Technique                       | How it works |
| ------------------------------- | ------------ |
| **Preload / spring loading**    | Spring force presses the pinion/worm into the wheel, taking up the gap on one flank (e.g. a spring-loaded worm pressed toward the worm wheel). |
| **Split / scissor gears**       | Two gear halves on one shaft, sprung apart so their teeth bear on *opposite* flanks of the mating tooth — eliminates the gap without changing the ratio. Common as **split anti-backlash worm** and split spur gears. |
| **Dual-motor (electronic preload)** | Two motors drive one output and are commanded to push slightly against each other, removing the dead zone electronically. |
| **Choose a zero-backlash mechanism** | The cleanest fix: cycloidal (near-zero) or harmonic (zero) instead of correcting a backlash-prone train. |

(SDP/SI anti-backlash worm gears; FirgelliAuto split worm; ROBOMECH switchable-backdrive
worm — see Sources.)

### 4.2 Worm gear — the self-locking special case

A worm drive **cannot be backdriven**: "a worm gear cannot be backdriven because of the
friction between tooth surfaces," so it "maintains a joint angle without energy
consumption." For a base or shoulder that must **hold a pose with the motor unpowered**
(safety, holding heavy payloads, e-stop position retention) this is a genuine feature — at
the cost of low efficiency (η ≈ 0.4–0.7) and zero compliance/backdrivability (bad for
cobot-style collision safety). Trade deliberately. (Springer ROBOMECH — see Sources.)

---

## 5. Microstepping caveat — resolution, NOT accuracy

This is the most-misunderstood number in the chain. Microstepping subdivides each full
step by energizing the two phases with sine/cosine currents. It **improves smoothness and
commanded resolution**, but it does **not** improve positioning **accuracy or
repeatability** proportionally — and beyond a point it improves them not at all.

**Primary-source statement (FAULHABER):** *"Despite the higher resolution that can be
achieved by the smaller steps, the accuracy of a stepper motor does not increase in
microstepping operation. Quite the opposite: the accuracy may even decrease."*

### 5.1 Why — the incremental-torque collapse

The torque holding the rotor at a commanded microstep is (ideally) sinusoidal in the
angular error between the rotor and the commanded electrical angle. One full step spans
**90 electrical degrees**, so dividing a full step into `N` microsteps puts the first
microstep's *available restoring torque* at roughly:

```text
T_incremental ≈ T_holding × sin(90° / N)
```

where `T_holding` is the full-step holding torque and `N` is microsteps per full step.
This collapses fast:

| N (microsteps/full step) | sin(90°/N) | Incremental torque vs. full-step |
| ------------------------ | ---------- | -------------------------------- |
| 1 (full step)            | sin(90°)=1.000 | 100% |
| 2                        | sin(45°)=0.707 | 71%  |
| 8                        | sin(11.25°)=0.195 | **~20%** |
| 16                       | sin(5.625°)=0.098 | ~10% |
| 256                      | sin(0.352°)=0.0061| ~0.6% |

The `N=8 → 0.195` row **corroborates** FAULHABER's independent statement that
*"microstepping operation with just eight microsteps already reduces the static torque to
less than 20 percent."* The sine model and the primary source agree.

### 5.2 The consequence — load-induced position error (deadband)

Because the restoring torque per microstep is tiny, **any load torque displaces the rotor
from the commanded microstep** until enough angular error builds to generate matching
torque — a "magnetic backlash." FAULHABER: *"Any load torque will result in a magnetic
'backlash', displacing the rotor from the intended position until sufficient torque is
generated."* And: when *"the sum of load torque, motor friction and cogging torque is
greater than the incremental torque,"* the rotor may **not move at all** for one
microstep — so the commanded fine resolution is fictional under load.

### 5.3 What this means for the design

- **Real, repeatable accuracy is bounded by the FULL-STEP angle through the reduction**,
  not the microstep angle:
  ```text
  resolution_fullstep_deg = 360 / (full_steps_per_rev × gear_ratio)
  ```
- Use microstepping for **smoothness and quieter motion**, and for resolution *down to
  the point load torque can still hold it* — but **buy accuracy with gear ratio (and
  low-backlash mechanisms), not with more microsteps.**
- 16 microsteps is the standard sweet spot; going past 32 buys smoothness, essentially no
  extra usable accuracy. (FAULHABER; Analog Devices *Mastering Precision*; Lin Engineering;
  EDN — see Sources.)

---

## 6. Worked generic example

**Setup:** NEMA17 1.8° motor (`full_steps_per_rev = 200`), driver at **16 microsteps**,
**5:1** reduction (e.g. 16T → 80T belt, `gear_ratio = 5`).

### 6.1 The two resolutions, side by side

```text
steps_per_deg              = (200 × 16 × 5) / 360 = 16000 / 360 = 44.44 microsteps/deg
resolution_commanded_deg   = 360 / (200 × 16 × 5) = 360 / 16000 = 0.0225°  ← firmware COMMANDS this
resolution_fullstep_deg    = 360 / (200 × 1  × 5) = 360 / 1000  = 0.36°    ← real accuracy bound (pre-backlash)
```

So the firmware can *command* 0.0225° increments, but the joint can only **repeatably
hold** to ~0.36° before backlash — a **16× gap** between the pretty number and the real
one. That gap *is* the microstepping caveat made concrete.

Arc length at a 300 mm reach, commanded vs. real:

```text
arc_commanded = 300 × 0.0225 × π/180 ≈ 0.118 mm
arc_fullstep  = 300 × 0.36   × π/180 ≈ 1.88 mm
```

### 6.2 Moving the knobs

**Double the microstepping (16 → 32):**

```text
resolution_commanded_deg = 360 / (200 × 32 × 5) = 0.01125°   ← HALVED (twice as fine, commanded)
resolution_fullstep_deg  = 360 / (200 × 1  × 5) = 0.36°      ← UNCHANGED (real accuracy did not move)
```

More microsteps cut the commanded number in half but leave real accuracy at 0.36° —
exactly the lesson of §5.

**Double the gear ratio instead (5:1 → 10:1):**

```text
resolution_commanded_deg = 360 / (200 × 16 × 10) = 0.01125°  ← HALVED
resolution_fullstep_deg  = 360 / (200 × 1  × 10) = 0.18°     ← HALVED TOO — real accuracy actually improved
steps_per_deg            = (200 × 16 × 10) / 360 = 88.89 microsteps/deg
```

Doubling the **ratio** halves *both* numbers — it buys **real** accuracy (and torque),
which doubling microsteps cannot. **This contrast is the entire design takeaway: spend
mechanical reduction to gain accuracy; spend microsteps only to gain smoothness.**

### 6.3 Feeding the firmware

The output of this chain is the firmware's per-joint `steps_per_deg` configuration field:

```text
steps_per_deg = (full_steps_per_rev × microsteps × gear_ratio) / 360
```

(44.44 for the 16-microstep/5:1 example; 88.89 if you go 10:1.) That single number tells
the controller how many driver pulses equal one degree of joint motion. Its reciprocal
(`resolution_commanded_deg`) is the finest *commanded* increment; the **full-step** version
(`resolution_fullstep_deg`) and the joint's **backlash** together bound the **achievable
precision** the calculator should report alongside it — never report the microstep number
alone as "accuracy."

---

## 7. Quick-reference formula sheet

```text
# Forward
steps_per_deg            = (full_steps_per_rev × microsteps × gear_ratio) / 360
resolution_commanded_deg = 360 / (full_steps_per_rev × microsteps × gear_ratio) = 1 / steps_per_deg
resolution_fullstep_deg  = 360 / (full_steps_per_rev × gear_ratio)           # real accuracy bound
arc_length_mm            = R × resolution_deg × (π / 180)

# Inverse (design)
gear_ratio   = (steps_per_deg × 360) / (full_steps_per_rev × microsteps)
microsteps   = (steps_per_deg × 360) / (full_steps_per_rev × gear_ratio)
resolution_deg_max = (tolerance_mm / R) × (180 / π)      # required res from a gripper tolerance budget

# Belt ratio from tooth counts (driven : motor)
gear_ratio   = driven_pulley_teeth / motor_pulley_teeth

# Microstep incremental-torque collapse (N microsteps per full step; full step = 90 elec. deg)
T_incremental ≈ T_holding × sin(90° / N)

# Repeatability budget
repeatability ≈ resolution_fullstep_deg + backlash_deg
```

Defaults for the calculator: `full_steps_per_rev = 200` (or 400 for 0.9° motors),
`microsteps = 16`, `gear_ratio` per §3.4, `R` per joint from the arm geometry.

---

## Sources

**Steps/rev, microstepping basics, and the steps-per-deg identity**

- Klipper — *Rotation Distance* — <https://www.klipper3d.org/Rotation_Distance.html> —
  canonical `full_steps_per_rotation` (200 / 400), `microsteps` (16 typical), and
  `gear_ratio` as **driven:motor** with the `80:16` (5:1) belt example. Load-bearing for
  §1 and §1.3.
- Mosaic Industries — *Stepper Motor Specifications (NEMA 17, 1.8°, 200 steps/rev)* —
  <http://www.mosaic-industries.com/embedded-systems/microcontroller-projects/stepper-motors/specifications> —
  confirms 1.8° = 200 full steps/rev.
- SkysMotor — *Impact of Microstepping on Motion Smoothness in NEMA 17* —
  <https://www.skysmotor.co.uk/article-114-The-Impact-of-Microstepping-on-Motion-Smoothness-in-Nema-17-Stepper-Motors.html> —
  256× microstep = 0.007°/microstep = 51,200 microsteps/rev; microstepping aids smoothness.

**Microstepping does NOT add accuracy (§5) — primary sources**

- FAULHABER — *Stepper Motor Tutorial: Eight Facts and Myths Surrounding Microstepping* —
  <https://www.faulhaber.com/en/know-how/tutorials/stepper-motor-tutorial-eight-facts-and-myths-surrounding-microstepping-operation/> —
  **primary**: "accuracy does not increase… may even decrease"; "8 microsteps already
  reduces the static torque to less than 20 percent"; load-torque "magnetic backlash"
  deadband. Verified by direct fetch.
- Analog Devices — *Mastering Precision: Understanding Microstepping* —
  <https://www.analog.com/en/resources/analog-dialogue/articles/mastering-precision-understanding-microstepping.html> —
  resolution-vs-accuracy, sinusoidal incremental torque, harmonic distortion.
- EDN — *Why microstepping in stepper motors isn't as good as you think* —
  <https://www.edn.com/why-microstepping-in-stepper-motors-isnt-as-good-as-you-think/> —
  the canonical "resolution up, accuracy not" article. *(Page repeatedly timed out on
  fetch; cited from search excerpt + corroborated by FAULHABER/ADI — the `sin(90°/N)`
  incremental-torque model in §5.1 is the standard relation, cross-checked against
  FAULHABER's <20%-at-8-microsteps figure, not lifted from this page.)*
- Lin Engineering — *Methods for Increasing Accuracy in Stepper Motors* —
  <https://www.linengineering.com/news/methods-for-increasing-accuracy-in-stepper-motors> —
  "increasing resolution, not accuracy"; positional error unchanged from full to 1/32 step.

**Reduction mechanisms & DIY arm ratios (§3)**

- Eureka/PatSnap — *Harmonic drive vs planetary gear in robotic joints* —
  <https://eureka.patsnap.com/article/harmonic-drive-vs-planetary-gear-in-robotic-joints> —
  harmonic = zero backlash but low stiffness/efficiency; planetary = efficient/stiff but
  backlash; both low backdrivability.
- ResearchGate — *Cycloid vs. harmonic drives for high-ratio single-stage robotic
  transmissions* —
  <https://www.researchgate.net/publication/261416541_Cycloid_vs_harmonic_drives_for_use_in_high_ratio_single_stage_robotic_transmissions> —
  comparative tradeoffs in robot joints.
- Hackaday — *Triple Cycloidal Robot Arm* —
  <https://hackaday.io/project/166133-triple-cycloidal-robot-arm> — 30:1 / 27:1 cycloidal
  on NEMA17; cycloidal printability.
- Thingiverse — *132:1 Hypocycloid gearbox for NEMA17* —
  <https://www.thingiverse.com/thing:371422> — printable high single-stage ratio.
- The White Owls — *Ultimate Guide to Design Cycloidal Drives* —
  <https://ewhiteowls.com/2022/02/the-ultimate-guide-to-design-cycloidal-drives-the-beating-heart-of-robotic-arms/> —
  cycloidal as the DIY-printable precision choice; 20:1 near-zero backlash, ~5 N·m, 48:1 example.
- FrankHuai — *AR4 Robot Geared Stepper NEMA 17 Ratio 50:1* —
  <https://www.frankhuai.com/ar4-robot-geared-stepper-motor-nema-17-ratio-50-1> — 50:1
  geared NEMA17 on a real 6-DOF arm (base/shoulder-class ratio).
- Kingroon — *Top 3D Printed Robot Arm Projects* —
  <https://kingroon.com/blogs/3d-printing-guides/top-3d-printed-robot-arm-projects> —
  survey of printed-arm reduction choices.

**Backlash, anti-backlash & worm self-locking (§4)**

- Springer ROBOMECH — *Worm gear mechanism with switchable backdrivability* —
  <https://link.springer.com/article/10.1186/s40648-019-0149-7> — **primary** for worm
  self-locking: holds joint angle with zero power; not backdrivable due to tooth friction.
- FirgelliAuto — *Three-part Worm Screw Mechanism (split anti-backlash worm)* —
  <https://www.firgelliauto.com/blogs/mechanisms/three-part-worm-screw> — split-worm
  preload removes backlash without changing ratio/self-locking.
- SDP/SI — *Anti-Backlash Worm Gear Pairs* —
  <https://shop.sdp-si.com/products/gears-differentials-pinions-racks/worm-gear-pairs/worms-anti-backlash.html> —
  commercial spring-preloaded anti-backlash worms.

**Arc length / end-effector error (§2)**

- Wevolver — *AR2 robotic arm spec* — <https://www.wevolver.com/specs/ar2.robotic.arm> —
  reference 6-DOF NEMA17 arm geometry/joint reach.
- arXiv — *Arduino Controlled Pick-n-Place Robotic Arm* —
  <https://arxiv.org/pdf/2103.09970> — joint angular error → end-effector linear error
  propagation (~4.3 mm per 1.8° step data point used in §2.2).

**Calculators (cross-check arithmetic)**

- TH3D — *Klipper Rotation Distance Calculator* —
  <https://www.th3dstudio.com/klipper-rotation-distance-calculator/>
- Firgelli — *Stepper Motor Steps-Per-MM Calculator* —
  <https://www.firgelliauto.com/blogs/engineering-calculators/stepper-motor-steps-per-mm-calculator-cnc-and-3d-printer>

> **Uncertainty flags:** (1) The `T_incremental ≈ T_holding × sin(90°/N)` model in §5.1 is
> the standard idealized relation (full step = 90 electrical degrees, sinusoidal torque-vs-
> angle); real motors deviate due to detent torque, coil inductance, pole geometry, and
> non-sinusoidal torque — treat it as a first-order bound, corroborated by FAULHABER's
> measured "<20% at 8 microsteps," not an exact figure. (2) The EDN article is cited from
> search excerpts (page timed out on direct fetch); its claims are independently confirmed
> by FAULHABER, Analog Devices, and Lin Engineering. (3) The 0.05–0.1° "good enough"
> heuristic is a design rule of thumb, **not** a sourced hard threshold — always derive the
> real target from `tolerance_mm / R`. (4) Per-joint ratio bands in §3.4 are representative
> of surveyed DIY builds, not a standard.
