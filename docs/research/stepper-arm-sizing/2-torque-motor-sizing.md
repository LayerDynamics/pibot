# Torque & Motor Sizing for a DIY Stepper-Motor Robot Arm

**Scope:** Robot-agnostic engineering reference for sizing stepper motors (and their
gearboxes) on a revolute-joint robot arm. Written to back a configurable sizing spec and a
Python calculator, with a generic **NEMA17 6-DOF** baseline. All formulas are SI
(**N·m, kg, m, rad, s**); one conversion line is given where vendor data uses other units.

> **The one rule to remember.** Size every joint for its **worst case = arm horizontal,
> fully extended, holding the payload at full reach**, then reflect that joint torque to the
> motor through the gearbox. **Gear reduction is the dominant sizing lever**: it divides the
> required motor torque by the ratio (and divides reflected inertia by the ratio *squared*),
> at the cost of joint speed. Pick the ratio first; the motor frame size falls out of it.

---

## 0. Notation and units

| Symbol | Meaning | Unit |
|---|---|---|
| `g` | gravitational acceleration = 9.81 | m/s² |
| `m_i` | mass of link/motor/payload item *i* (everything **beyond** the joint) | kg |
| `d_i` | **horizontal** distance from the joint axis to item *i*'s center of mass | m |
| `θ` | joint angle measured from horizontal (0 = arm horizontal) | rad |
| `T_static` | gravity (holding) torque at the joint | N·m |
| `I` (or `J`) | mass moment of inertia about the joint axis | kg·m² |
| `α` | angular acceleration of the joint | rad/s² |
| `T_dyn` | inertial (acceleration) torque at the joint | N·m |
| `T_joint_req` | required torque **at the joint output** after safety factor | N·m |
| `SF` | safety / design factor (typ. 1.5–2.0) | — |
| `G` | gear reduction ratio (output rev : motor rev, e.g. 50 for 50:1) | — |
| `η` | gearbox mechanical efficiency (belt ~0.9, planetary ~0.7–0.8, worm low) | — |
| `T_motor_req` | required torque **at the motor shaft** | N·m |
| `T_hold` | motor rated **holding** torque (datasheet, at standstill, full current) | N·m |
| `u` | usable fraction of holding torque at the operating speed (speed derate) | — |

**Unit conversions (vendor data mixes these):**
`1 N·m = 141.6 oz·in = 10.197 kg·cm`. So a typical NEMA17 at **0.45 N·m ≈ 63.7 oz·in ≈ 4.6 kg·cm**.

---

## 1. Static / gravity (holding) torque per joint

A revolute joint must, at minimum, hold up the **dead weight of everything distal to it**
(all links, motors, gripper, and payload past that joint). Each distal mass `m_i` whose
center of mass is a horizontal distance `d_i` from the joint axis contributes a gravitational
moment `m_i · g · d_i`. Summing:

```text
T_static(θ) = g · cos(θ) · Σ_i ( m_i · d_i )
```

- `Σ_i` runs over **every** mass beyond the joint (links + their motors + gripper + payload).
- `d_i` is the **horizontal** lever arm to mass *i*'s CG.
- The `cos(θ)` term is the angle dependence: at `θ = 0` (arm horizontal) the lever arms are
  fully horizontal and torque is **maximum**; at `θ = ±90°` (arm vertical) `cos = 0` and
  gravity torque vanishes. **Size at `θ = 0`:**

```text
T_static_worst = g · Σ_i ( m_i · d_i )        # arm horizontal, fully extended
```

This is the single most important load term for a robot arm and it is why the **base/shoulder
joints are by far the worst case** while distal (wrist) joints are light:

- **Base yaw (J1):** rotates about a (usually) **vertical** axis. Gravity produces **no**
  holding torque about a vertical axis — J1 is sized by *inertia/acceleration* and friction,
  not gravity. (If the base axis is tilted, include the gravity component.)
- **Shoulder (J2):** carries the **entire** distal arm + payload at the **longest** lever
  arms → **largest** `Σ(m_i d_i)` → **worst-case torque in the whole arm.**
- **Elbow (J3):** carries the forearm + wrist + payload; large but less than the shoulder.
- **Wrist (J4–J6):** carry only the small distal cluster + payload at short lever arms →
  **small** torque; this is why a 6-DOF arm uses big motors low and small motors high.

> Worked numbers for a generic shoulder are in §6.

**Caveat / convention:** the `cos(θ)` form assumes a single revolute joint with a horizontal
axis and the arm in a vertical plane. For a full multi-link arm the *exact* per-joint gravity
torque comes from the manipulator's gravity vector `G(q)` in the rigid-body dynamics
(`τ = M(q)q̈ + C(q,q̇)q̇ + G(q)`); the `Σ m_i d_i` sum is the standard, conservative
hand-calculation of the worst-case term of `G(q)` and is what hobby/DIY builds size to.
(Sources: ThinkRobotics, FIRGELLI, Physics Forums — §Sources.)

---

## 2. Dynamic (acceleration) torque, and total joint torque

To *accelerate* the joint you must also supply inertial torque:

```text
T_dyn = I · α
```

where `I` is the mass moment of inertia of all distal mass **about the joint axis** and `α`
is the commanded angular acceleration.

### 2a. Estimating `I` about the joint axis

Add up the contributions of the distal items. Two standard idealizations (HyperPhysics,
University Physics / LibreTexts):

| Body | Axis | Moment of inertia |
|---|---|---|
| **Point mass** (motor, gripper, payload lumped at radius `d`) | at distance `d` | `I = m · d²` |
| **Thin rod / link**, length `L`, rotating about **one end** | through the end | `I = m·L² / 3` |
| **Thin rod / link**, length `L`, rotating about its **center** | through center | `I = m·L² / 12` |
| **Solid cylinder/disc**, radius `r`, about its axis | symmetry axis | `I = ½ m·r²` |

For a quick conservative sizing, the **point-mass sum** is usually enough:

```text
I ≈ Σ_i ( m_i · d_i² )       # lump each distal item as a point mass at its CG radius
```

Add `m·L²/3` for any link whose own length is a significant fraction of the lever arm (a long
slender link about its proximal joint). Use the **parallel-axis theorem**
`I = I_cg + m·d²` if you have a body's CG inertia `I_cg` and offset `d`.

### 2b. Total required joint torque + safety factor

Worst case superimposes "hold gravity" **and** "accelerate" simultaneously:

```text
T_joint_worst = T_static_worst + T_dyn = g·Σ(m_i d_i) + I·α

T_joint_req   = SF · T_joint_worst              # apply the design factor here
```

- **Safety factor `SF` = 1.5–2.0** is the standard robotics rule of thumb (covers
  CG/mass estimation error, friction, cable drag, off-axis loads, manufacturing slop).
  (ThinkRobotics, FIRGELLI.)
- Keep `SF` a **separate, exposed parameter** from the motor speed-derate `u` (§4) — they
  cover different uncertainties and **must not be lumped**, or the calculator becomes
  un-tunable and the physics is hidden.

---

## 3. Reflecting joint torque to the motor through gearing (the key lever)

A gearbox of ratio `G` and efficiency `η` multiplies motor torque by `G·η` at the output, so
the torque the **motor** must produce to deliver `T_joint_req` is:

```text
T_motor_req = T_joint_req / (G · η)
```

- **Higher `G` → smaller required motor torque** (and finer resolution) → you can use a
  smaller frame size (NEMA17 instead of NEMA23). **This is the dominant sizing decision.**
- **The trade-off is speed:** output speed `ω_out = ω_motor / G`. A 50:1 box that makes a
  NEMA17 hold 5–7 N·m at the joint also means the joint turns 50× slower than the motor. So
  pick `G` to satisfy **both** the torque budget and the required joint speed.
- **Efficiency `η`** is real torque you lose to the gearbox: timing-belt/pulley ~0.9,
  spur/planetary ~0.7–0.8 (per stage), **worm gears low** (often 0.4–0.7) but self-locking,
  which is attractive for holding gravity loads without motor current. Cycloidal/harmonic
  drives (common on bigger arms) ~0.7–0.9. Use the *de-rated* `η`, not the marketing number.
- **Backlash** (not a torque term) still matters: it degrades positioning, so DIY arms favor
  belts, planetary, harmonic, or anti-backlash gears over plain spur/worm where precision
  counts.

(Sources: reflected-inertia/efficiency — ScienceDirect "Referred Inertia",
ContinuallyLearning Reflected-Inertia; geared-NEMA examples — StepperOnline, AR4.)

---

## 4. Stepper holding torque, derating, and what's actually *usable*

### 4a. Rated holding torque by frame size

`T_hold` is the **maximum static torque at standstill with rated current** — the headline
datasheet number. Typical hobby/DIY ranges:

| Frame | Typical holding torque | Notes |
|---|---|---|
| NEMA17 "pancake" (short, ~20 mm) | ~0.1–0.2 N·m | low torque, light/distal joints |
| **NEMA17** (40–48 mm body) | **~0.4–0.65 N·m** (≈57–92 oz·in) | the 6-DOF DIY workhorse |
| **NEMA23** | **~1.2–3.0 N·m** (≈170–425 oz·in) | base/shoulder/elbow on bigger arms |
| NEMA24 / NEMA34 | ~3–8+ N·m | large arms, beyond this reference's scope |

(StepperOnline / components101 NEMA17 datasheets; RobotDigg; AR4 build.)

### 4b. Three *different* derates — keep them straight

This is the most commonly mangled point, so state it precisely:

1. **Speed derate (the real sizing limiter).** Holding torque is a **standstill** number.
   As speed rises, winding inductance limits current and torque falls along the
   **torque–speed curve** (the *pull-out* curve): high torque at low speed, sloping down to
   little torque at high speed. Beyond the pull-out curve the motor **stalls / loses steps**.
   *(mechtex; motioncontroltips.)* For sizing, require the motor to deliver `T_motor_req` at
   the **actual operating speed**, i.e. budget against a **usable fraction**:

   ```text
   T_budget = T_hold · u          # u = usable fraction at operating speed
   ```

   A conservative DIY rule of thumb is **`u ≈ 0.5`** (size to ~half of rated holding); if the
   joint runs slow (typical for a geared arm) you may justify **`u ≈ 0.6–0.7`**. Treat `u` as
   a **tunable parameter, ideally replaced by the datasheet torque–speed curve** at your RPM.
   *(The 50–70% figure is a derate convention; the authoritative number is the manufacturer's
   curve — mark as approximate.)*

2. **Microstepping does NOT reduce the holding-torque envelope.** A microstepping driver
   **cannot change** the motor's physical holding torque (StepperOnline: *"the theoretical
   holding torque … is determined by its physical design, which microstepping drivers cannot
   alter"*). What microstepping changes is:
   - **Incremental (per-microstep) torque / positioning stiffness.** Holding torque varies
     sinusoidally with rotor offset, so the torque available to *resist one microstep of
     deflection* scales as **`T_inc ≈ T_hold · sin(90°/N)`** for `N` microsteps per full step
     (derived from the standard sinusoidal torque-angle model — *not* a vendor-stated
     formula; label it as such). Numerically:

     | Microsteps/full-step `N` | `sin(90°/N)` (fraction of `T_hold`) |
     |---|---|
     | 1 (full step) | 1.000 |
     | 2 | 0.707 |
     | 4 | 0.383 |
     | 8 | 0.195 |
     | 16 | 0.098 |
     | 32 | 0.049 |

     This means **fine microstepping buys smoothness/resolution, not load capacity** — under
     a steady gravity load the rotor simply sits at the offset where average torque balances
     the load; the *peak* (full-step) holding capacity is unchanged. So size gravity holding
     against `T_hold·u`, **not** against `T_inc`.
   - **Holding-torque ripple ~10–30%** across microstep positions (smd.ee: *"deviations of
     the holding torque in microstepping mode are usually 10–30 % of the maximum torque"*).

3. **Resultant-of-two-phases.** With two phases energized at currents `a, b`, the resultant
   holding torque is `T_h = √(a² + b²)` (smd.ee) — the basis of microstep current vectoring.

**Net rule for sizing:** budget gravity + acceleration against the **speed-derated holding
torque** `T_hold·u`; use microstepping for resolution/smoothness and do **not** count on it
for (nor penalize it against) load capacity.

### 4c. The sizing inequality

A motor+gearbox is adequate for a joint when:

```text
T_hold · u  ≥  T_motor_req  =  T_joint_req / (G · η)
              =  SF · ( g·Σ(m_i d_i) + I·α ) / (G · η)
```

NEMA17 → NEMA23 selection: if no sane gear ratio (one that still meets the joint **speed**
requirement) makes a ~0.45 N·m NEMA17 satisfy the inequality, **step up to NEMA23** (and a
higher-current external driver — see §5).

---

## 5. Moment of inertia & **reflected inertia** to the motor

Gearing tames inertia even harder than it tames torque, which is why a high ratio also makes a
joint *accelerate* well from a small motor. The load inertia seen **at the motor shaft** is the
joint inertia divided by the ratio **squared**:

```text
I_reflected = I_joint / G²
```

(ScienceDirect "Referred Inertia"; ContinuallyLearning Reflected-Inertia; Oriental Motor
"Load Inertia". The same relation read the other way: the motor's own rotor inertia `J_m`
appears at the joint as `G²·J_m`.)

Consequences for acceleration sizing:

- The motor's acceleration-torque burden is `T_acc_motor = (I_joint/G² + J_m) · α_motor`,
  where `α_motor = G·α_joint`. The `1/G²` crushes the (usually dominant) link/payload inertia,
  so for moderate-to-high `G` the **gravity term of §1 dominates the motor sizing**, and
  inertia is a second-order correction — exactly the regime DIY arms live in.
- **Inertia matching:** for snappy, well-damped motion the classic target is
  `I_reflected ≈ J_m` (reflected load inertia comparable to rotor inertia); ratios up to ~5–10:1
  reflected:rotor are commonly tolerated. Very high `G` can over-reduce, making rotor inertia
  dominate and wasting torque accelerating the motor itself. (Oriental Motor.)
- Net: choose `G` to satisfy **(a)** the torque inequality §4c, **(b)** the joint speed, and
  **(c)** a sane inertia match — usually (a) and (b) bind first on a DIY arm.

---

## 6. Worked generic example — horizontal 6-DOF arm, shoulder joint

**Configuration (generic NEMA17 baseline, arm horizontal & fully extended):**

| Distal item (beyond shoulder) | mass `m_i` (kg) | horiz. lever `d_i` (m) | `m·d` (kg·m) | `m·d²` (kg·m²) |
|---|---|---|---|---|
| Upper-arm link + its structure (CG) | 0.40 | 0.13 | 0.052 | 0.0068 |
| Elbow motor (NEMA17-class) | 0.30 | 0.25 | 0.075 | 0.0188 |
| Forearm link (CG) | 0.30 | 0.40 | 0.120 | 0.0480 |
| Wrist cluster (2–3 small motors) | 0.30 | 0.50 | 0.150 | 0.0750 |
| **Payload @ full reach** | 0.50 | 0.55 | 0.275 | 0.1513 |
| **Σ** | | | **0.672** | **0.300** |

**Static (gravity) shoulder torque, worst case:**

```text
T_static = g · Σ(m·d) = 9.81 × 0.672 ≈ 6.59 N·m
```

**Dynamic torque** (point-mass inertia `I ≈ Σ m·d² ≈ 0.300 kg·m²`, modest `α = 2 rad/s²`):

```text
T_dyn = I·α = 0.300 × 2 ≈ 0.60 N·m         # ~9% of the gravity term — gravity dominates
```

**Required joint torque with SF = 1.5:**

```text
T_joint_req = 1.5 × (6.59 + 0.60) ≈ 10.8 N·m   (≈14.4 N·m at SF = 2.0)
```

### 6a. Pick a gear ratio so a NEMA17 (~0.45 N·m) covers it

Reflect to the motor (`η = 0.8` planetary). Budget against `T_hold·u` with `T_hold = 0.45`:

| `G` (chosen for…) | `T_motor_req = T_joint_req/(G·η)` | NEMA17 budget `0.45·u` | Verdict |
|---|---|---|---|
| **50:1** (torque, slow joint) | 10.8 / (50·0.8) = **0.27 N·m** | u=0.5 → 0.225; u=0.6 → 0.27; u=0.7 → 0.32 | **Marginal at u=0.5; OK at u≥0.6** |
| 20:1 (more joint speed) | 10.8 / (20·0.8) = **0.67 N·m** | 0.45·0.7 = 0.32 | **Busts NEMA17 → NEMA23** |
| 10:1 (fast joint) | 10.8 / (10·0.9) = **1.20 N·m** | — | **NEMA23 territory** |

**Read this honestly — `u` is the deciding constraint.** At the conservative headline derate
`u = 0.5` the budget is `0.45 × 0.5 = 0.225 N·m`, which is **below** the 0.27 N·m the 50:1
motor needs — a NEMA17 would be marginal-to-failing. But a **50:1 shoulder turns slowly** (the
joint runs at `ω_motor / 50`), so the motor lives at the high-torque end of its torque–speed
curve where `u ≈ 0.6–0.7` is justified — and there the budget (0.27–0.32 N·m) **clears** the
0.27 N·m requirement. **That slow-joint, high-`u` regime is precisely why a real arm gets away
with a NEMA17 here:** the **Annin Robotics AR4** ships **NEMA17 + 50:1 planetary** on a
representative main joint (1 kg payload, 600 mm reach), strong corroboration that a ~0.45 N·m
NEMA17 behind a ~50:1 reduction is the right class for a shoulder of this scale.

On margins, state the basis explicitly: 0.45 N·m of full holding torque is **×1.7** over the
SF-factored, reflected requirement (0.45 / 0.27), or **≈×2.5** over the **un-factored**
reflected requirement (`T_joint_worst/(G·η) = 7.19 / (50·0.8) ≈ 0.18 N·m` → 0.45 / 0.18). If
you want a clean pass at the conservative `u = 0.5`, push to **G ≈ 60:1** (→ 0.225 N·m, exactly
at budget) or step to a **0.55–0.65 N·m NEMA17** (§4a) for a true ×2 at `u = 0.5`. *(AR4
per-joint ratios/torques vary by joint and the kit mixes NEMA17 and NEMA23 — treat the 50:1
NEMA17 as the verified representative data point, not an exact per-joint spec.)*

### 6b. When you're forced to NEMA23 + external driver

You drop off NEMA17 the moment the **required joint torque rises** or you **lower the ratio
for speed**:

- **Lower gear ratio for a faster joint** (20:1 → 0.67 N·m, 10:1 → 1.20 N·m motor torque):
  past NEMA17's usable budget → **NEMA23** (~1.2–3 N·m holding).
- **Heavier payload / longer reach** (raise `Σ m·d`) → higher `T_static` → same outcome.
- **Higher acceleration target** (raise `α`) — though with high `G` the `I·α/G²` reflected
  inertia stays small, so this rarely drives the choice alone.

A NEMA23 typically needs a **higher-current external stepper driver** (e.g. a
DM542/DM556-class 4–5.6 A digital driver) rather than the small integrated/StepStick drivers
that suffice for NEMA17. So the chain is: **payload + reach + speed → `T_joint_req` → pick `G`
→ `T_motor_req` → frame size (NEMA17 vs 23) → driver class**, and `G` simultaneously sets your
**joint resolution** (`step_angle / (G · microsteps)`) **and top speed** (`ω_motor_max / G`).

---

## 7. Sizing procedure (what the Python calculator implements)

For each joint, worst case = horizontal & fully extended:

1. **Build the distal mass table** `{(m_i, d_i)}` (links + motors + gripper + payload at full
   reach), from the base outward — every joint's table is a subset of the one below it.
2. `T_static = g · Σ(m_i · d_i)` (skip/zero for a purely vertical base axis).
3. `I = Σ(m_i · d_i²)` (+ `m·L²/3` for long slender links); `T_dyn = I · α_target`.
4. `T_joint_req = SF · (T_static + T_dyn)`  — **SF a free param, 1.5–2.0**.
5. For a candidate `(G, η)`: `T_motor_req = T_joint_req / (G · η)`;
   `I_reflected = I / G²`.
6. **Accept** the motor if `T_hold · u ≥ T_motor_req` — **`u` a free param (~0.5, or read the
   torque–speed curve at the joint's RPM)** — *and* the resulting joint speed
   `ω_motor_max / G` meets the motion spec *and* the inertia match `I_reflected/J_m` is sane.
7. If no `(G, motor)` satisfies all three with a NEMA17, **escalate to NEMA23 + external
   driver**. Report joint resolution `= 1.8° / (G · microsteps)` and top speed for the chosen
   `G`.

Expose as configurable: link masses/lengths, motor masses, payload, reach, `α_target`, `SF`,
`u`, `η`, `G` candidates, `T_hold` per frame, `microsteps`. Defaults = the generic NEMA17
6-DOF baseline of §6.

---

## Sources

Real pages fetched/searched (June 2026). Notes flag what each does and does not support.

- **ThinkRobotics — "Basics of Motor Sizing and Selection for Robots"**
  <https://thinkrobotics.com/blogs/learn/basics-of-motor-sizing-and-selection-for-robots-a-complete-engineering-guide>
  — torque = weight × distance from axis; `τ_dynamic = τ_static + I·α`; worst case = fully
  extended horizontal; **safety factor 1.5–2** rule of thumb.
- **FIRGELLI — Robot Arm Payload / Joint-Torque calculators**
  <https://www.firgelliauto.com/blogs/engineering-calculators/robot-arm-payload-calculator-joint-torque>
  ,
  <https://www.firgelliauto.com/blogs/calculators/joint-torque-from-payload-calculator>
  — `m·g·d·cos(θ)` gravity-moment form; cumulative distal-mass summation per joint.
- **Physics Forums — "How to calculate required torque for a robot arm"**
  <https://www.physicsforums.com/threads/how-to-calculate-required-torque-for-a-robot-arm.1056783/>
  — community confirmation of the cumulative `Σ m·d` hand method and worst-case extension.
- **HyperPhysics — Moment of Inertia: Rod**
  <http://hyperphysics.phy-astr.gsu.edu/hbase/mi2.html>
  — rod about end `mL²/3`, about center `mL²/12`.
- **Physics LibreTexts / University Physics Vol 1 — Calculating Moments of Inertia**
  <https://phys.libretexts.org/Courses/Muhlenberg_College/MC:_Physics_121_-_General_Physics_I/11:_Fixed-Axis_Rotation__Introduction/11.06:_Calculating_Moments_of_Inertia>
  ,
  <https://pressbooks.online.ucf.edu/osuniversityphysics/chapter/10-5-calculating-moments-of-inertia/>
  — point mass `mr²`, rod `mL²/3` & `mL²/12`, parallel-axis theorem.
- **Oriental Motor — "Motor Sizing Basics Part 2: Load Inertia"**
  <https://blog.orientalmotor.com/motor-sizing-basics-part-2-load-inertia>
  — load (moment of) inertia and acceleration-torque sizing. *Note: the page renders its
  equations as images; the cylinder/rod inertia forms here are taken from the physics
  references above, which agree.*
- **ScienceDirect Topics — "Referred Inertia"**
  <https://www.sciencedirect.com/topics/engineering/referred-inertia>
  — reflected/referred inertia at the motor = rotor inertia + load inertia scaled by `G²`
  (`I_reflected = I_load / G²`, motor-side view `G²·J_m`).
- **ContinuallyLearning — Reflected Inertia (robotics notes)**
  <https://continuallylearning.github.io/Robotics/Reflected-Inertia>
  — `G²Jm` reflected-inertia derivation and the responsiveness trade-off of high `G`.
- **mechtex — "Understanding Torque and Speed Curves in Stepper Motors"**
  <https://mechtex.com/blog/understanding-torque-and-speed-curves-in-stepper-motors>
  — holding vs pull-in vs pull-out torque; torque falls with speed (downward-sloping curve);
  stall/step-loss past pull-out. *Note: gives no single "usable %" — that's a convention.*
- **MotionControlTips — "What kind of torque can I get out of a stepper motor…"**
  <https://www.motioncontroltips.com/faq-kind-torque-can-get-stepper-motor-versus-options/>
  — stepper torque highest at low speed, decays with speed (corroborates the speed-derate).
  *Note: page returned HTTP 403 on direct fetch; used as a titled search result, not quoted
  verbatim — treat as secondary.*
- **StepperOnline Help — "The Impact of Microstepping on Stepper Motor Torque"**
  <https://help.stepperonline.com/en/article/the-impact-of-microstepping-on-stepper-motor-torque-125kmb7/>
  — **microstepping does NOT change theoretical holding torque** (physical-design limited);
  it improves *effective running* smoothness, not load capacity. *Key correction to the naive
  "microstepping loses torque" framing.*
- **smd.ee — "Microstepping operation of stepper motors"**
  <https://smd.ee/info/articles/microstepping-operation-of-stepper-motors>
  — two-phase resultant `T_h = √(a²+b²)`; **holding-torque deviation 10–30%** across microstep
  positions. *Note: the `T_hold·sin(90°/N)` per-microstep table in §4b is derived from the
  sinusoidal torque-angle model, not stated verbatim by this page — labeled as derived.*
- **StepperOnline — NEMA17 geared stepper (planetary 5:1, 20:1, 50:1) product pages**
  <https://omc-stepperonline.com/Nema-17-Stepper-Motor-L39mm-Gear-Ratio-201-High-Precision-Planetary-Gearbox.html>
  — real NEMA17 holding-torque (~0.4–0.65 N·m) and planetary gear-ratio options; 1.68 A.
- **components101 — NEMA17 Stepper Motor Datasheet**
  <https://components101.com/motors/nema17-stepper-motor>
  — 1.8°/step (200 steps/rev), ~0.4 N·m-class holding torque, current/voltage specs.
- **Annin Robotics AR4 (frankhuai geared-motor listing; RoboDK spec)**
  <https://www.frankhuai.com/ar4-robot-geared-stepper-motor-nema-17-ratio-50-1>
  ,
  <https://robodk.com/robot/Annin-Robotics/AR4>
  — real 6-DOF DIY arm: **NEMA17 + 50:1 planetary** main-joint motors, **1 kg payload, 600 mm
  reach**, NEMA17/NEMA23 mix; StepperOnline-sourced. *Note: per-joint ratio/torque table not
  fetched (wiki/forum pages returned 403); the 50:1 NEMA17 data point is the verified anchor —
  per-joint values are approximate.*

### Marked uncertainties

- The **usable fraction `u` ≈ 0.5–0.7** is a *convention*, not a constant — the authoritative
  value is the specific motor's **torque–speed curve at the joint's operating RPM**. Treat the
  number as a placeholder for that curve.
- The **`T_hold · sin(90°/N)`** per-microstep table is **derived** from the standard sinusoidal
  torque-angle model; it is physically standard but not lifted verbatim from a cited vendor
  page. It governs positioning stiffness, **not** gravity-holding capacity.
- Per-joint **AR4** torques/ratios are approximate (the detailed wiki/forum pages 403'd);
  only the **NEMA17 + 50:1**, **1 kg / 600 mm** figures were directly corroborated.
- The single-joint **`cos(θ)`** gravity model is the standard hand-calc of the worst-case
  `G(q)` term; a multi-link arm's exact per-joint gravity torque needs the full rigid-body
  dynamics.
