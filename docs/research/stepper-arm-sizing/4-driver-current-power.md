# Driver Current, Microstepping & Power — DIY Stepper-Motor Robot Arm

Authoritative, formula-complete reference for sizing **driver current, microstepping,
and the power supply** of a DIY stepper-motor robot arm. Robot-agnostic and configurable:
feeds an engineering spec + a Python sizing calculator (generic NEMA17 6-DOF).

**Scope / assumptions for this reference**

- Controller class: **Creality 4.2.2-class boards** with onboard A4988- / TMC2208-class
  drivers (~1.2–2 A/phase capability).
- Larger joints (typically a **NEMA23 base**) require **external** drivers
  (TB6600 / DM542) fed step/dir from spare GPIO.
- Supply: **24 V** (standard for arm/printer steppers).
- All formulas below give variables + units. Where a number came from a search snippet
  rather than a page we actually fetched, it is flagged **[snippet, not primary]**.

> **Per-formula confidence:** The two Pololu product pages (A4988 #1182, DRV8825 #2133)
> were fetched directly and are primary. The TMC2209 RMS formula is **corroborated across
> ≥3 sources and verified algebraically** (see §1.3) but the primary datasheet PDF timed
> out on fetch — treat its exact constants as "consistent, not read from primary."
> Microstepping `sin(90°/N)`, the PSU rules, and the 24 V rationale come from search
> snippets of pages that returned HTTP 403 to direct fetch — flagged **[snippet]** inline.

---

## 0. The three "0.7" factors — keep them separate

A recurring source of error: three different ~0.7 factors all appear in stepper current
math and get conflated. They are independent:

| Factor | Value | What it is |
|---|---|---|
| RMS ↔ peak | `1/√2 ≈ 0.707` | A sine-driven coil's RMS current is `1/√2` of its peak. The TMC RMS formula contains this. |
| Full-step coil limiting (A4988) | `≈ 0.7` | At a full step both coils are on; the chopper limits **each** coil to ~70% of the set per-coil trip current. |
| Safety derate | `0.8–0.9` (i.e. lower current 10–20%) | Engineering headroom so the motor/driver run cool. A **choice**, not physics. |

**RMS-vs-peak, stated once and clearly:**
**A4988 / DRV8825 `Vref` sets the *peak* per-coil current trip point.**
**TMC2208 / TMC2209 `run_current` (and the UART formula) are specified in *RMS*.**
Mixing these is the #1 cause of a motor set to ~40% too hot or ~40% too weak.

---

## 1. Setting phase current

Stepper drivers are **current-limited (chopper) drivers**: you do *not* match supply
voltage to the motor's rated voltage. You set a **current limit** to the motor's rated
phase current, and the driver chops the (higher) supply voltage to hold that current.
Set the limit to roughly **70–90 % of the motor's rated phase current** for headroom
("leave some headroom and lower the current by around 10–20 %" — Circuitist).

### 1.1 A4988 (primary — Pololu product page #1182)

```text
I_max = V_ref / (8 × R_CS)          [peak per-coil trip current, A]
V_ref = 8 × I_max × R_CS            [set this on the trimpot, V]
```

- `V_ref` — voltage at the trimpot/reference pin (V), measured pot-wiper to GND.
- `I_max` — per-coil current limit (A), **peak**.
- `R_CS` — sense resistor. **Pololu A4988: 0.068 Ω** since 2017 (older green boards 0.050 Ω).
  Many clones use 0.1 Ω — **measure or read the board**, the constant changes the answer.

Worked: NEMA17 rated 1.5 A, derate to 1.3 A, Pololu 0.068 Ω →
`V_ref = 8 × 1.3 × 0.068 = 0.707 V`.

> **Full-step caveat (Pololu):** at a full step the chopper limits **each** coil to ~70 %
> of the set trip current, so the *per-coil* limit you set is not the per-coil current in
> all microstep phases. Set the limit to the motor's rated phase current and let the
> driver do the rest.

**Max continuous current (Pololu A4988 #1182):** "up to approximately **1 A per phase
without a heat sink or forced air flow**"; "rated for **2 A per coil with sufficient
additional cooling**."

### 1.2 DRV8825 (primary — Pololu product page #2133)

```text
I_max = 2 × V_ref                   ⇔   I_max = V_ref / (5 × R_CS)   with R_CS = 0.100 Ω
V_ref = I_max / 2                    [set this on the trimpot, V]
```

- `R_CS` on the Pololu DRV8825 is **0.100 Ω**, which is why the simplified form is
  `I_max = 2 × V_ref` (since `1 / (5 × 0.1) = 2`).
- The two general forms `V_ref/(8·R_CS)` (A4988) and `V_ref/(5·R_CS)` (DRV8825) are the
  *same physics* with different internal gains and Rsense — **the boards are not
  interchangeable.** A 1.5 A motor: A4988 (0.068 Ω) → `V_ref ≈ 0.82 V`; DRV8825 →
  `V_ref = 0.75 V`. Swapping the board without re-setting `V_ref` mis-currents the motor.

**Max continuous current (Pololu DRV8825 #2133):** "up to approximately **1.5 A per phase
without a heat sink or forced air flow**"; "rated for up to **2.2 A per coil with
sufficient additional cooling**."

### 1.3 TMC2208 / TMC2209 (current set in firmware/UART or by Vref)

TMC drivers are typically set by **firmware over UART** (Klipper/Marlin `run_current`),
not a trimpot. The current is **RMS**.

**Datasheet RMS form** (corroborated across ≥3 sources; primary PDF not read — see header):

```text
I_RMS = (V_VREF / 2.5 V) × (1/√2) × ( 325 mV / (R_SENSE + 20 mΩ) )      [A RMS]
```

- `325 mV` — full-scale sense voltage (high-sensitivity VSENSE; the low setting ≈ 180 mV
  is used on some boards to cut sense-resistor dissipation).
- `R_SENSE` — board sense resistor, **typically 0.110 Ω** on common SilentStepStick-class
  boards. The `+20 mΩ` is the internal parasitic offset.
- `1/√2` — the RMS↔peak factor (§0).

For 0.11 Ω boards this reduces to the widely-quoted convenience forms **[snippet]**:

```text
I_RMS ≈ 0.71 × V_VREF      ⇔      V_VREF ≈ 1.41 × I_RMS
```

(Algebraic check: `325/(110+20) × 1/√2 / 2.5 = 2.5 × 0.7071 / 2.5 = 0.707` ✓ — so the
`0.71 × V_VREF` snippet form is internally consistent with the datasheet form.)

**UART/firmware path:** current is programmed via the **IRUN current scale `CS` (0–31)**,
not a voltage. Conceptually `I_RMS ∝ (CS+1)/32 × full-scale`. The datasheet recommends
**IRUN in the 16–31 range** for good microstep current resolution. In Klipper you set
`run_current` (RMS amps) directly and the firmware computes `CS`. **[snippet]**

**Max settable current:** **1.77 A RMS** on 0.11 Ω boards; SilentStepStick-class modules
are practically limited to **~1.2 A RMS** continuous by thermals. **[snippet]**

**HOLD policy:** TMC `hold_current` (or A4988/DRV8825 with firmware idle-current-reduction)
sets a *reduced* standstill current. A typical hold is **~0.5–0.7 × run_current**; idle
reduction cuts standstill heat by roughly half. This is exactly the knob the arm's HOLD
policy uses (§4). **[snippet]**

---

## 2. Onboard vs external driver limits — the threshold

| Driver class | Continuous capability | Verdict |
|---|---|---|
| Onboard A4988 (Pololu) | ~1 A bare, **2 A/coil cooled** | NEMA17 ✓ |
| Onboard DRV8825 (Pololu) | ~1.5 A bare, **2.2 A/coil cooled** | NEMA17 ✓ |
| Onboard TMC2208/2209 | **~1.2 A RMS** practical (1.77 A absolute) | NEMA17 ✓ |
| External **TB6600** | up to **3.5–4.0 A** (selectable 0.7–4.0 A) | NEMA23 ✓ |
| External **DM542** | ~**4.0–4.5 A** peak | NEMA23 ✓ |

**State the threshold plainly:** onboard 4.2.2-class drivers are good to roughly
**1.5–2 A/phase (cooled)**. A motor needing more — the classic case being a **NEMA23 base
joint at ~2.8–3 A/phase** — **must** use an external TB6600/DM542. Wire it as a
**step/dir/enable** stage fed from a spare controller GPIO (the controller still sequences
the pulses; only the power stage moves off-board). Practical rule of thumb:

> **If rated phase current > ~2 A → external driver. NEMA17 → onboard; NEMA23 → external.**

A4988 will brown-out / thermal-shutdown trying to drive a 2.8 A NEMA23 — it is not a
matter of tuning, it is a hardware ceiling.

---

## 3. Microstepping vs torque / current

Microstepping subdivides each full step by driving the two phases with a **sine/cosine**
current pair, so the current vector rotates in small angular increments. **The total
current magnitude stays ~constant** across microstepping settings — microstepping does
**not** save or cost meaningful current.

### 3.1 Incremental torque per microstep falls

```text
T_incremental ≈ T_holding × sin(90° / N)     [torque available to move ONE microstep]
```

- `N` — microsteps per full step (e.g. 16, 32).
- `T_holding` — the motor's rated full-step holding torque.

| N (microsteps) | `sin(90°/N)` | Incremental torque vs full step |
|---|---|---|
| 1 (full) | sin 90° = 1.00 | 100 % |
| 8 | sin 11.25° | ~20 % |
| 16 | sin 5.625° | ~10 % |
| 32 | sin 2.8125° | ~5 % |

### 3.2 The critical distinction — do NOT misread the table

The `sin(90°/N)` figure is the torque to advance **a single microstep**, i.e. the
fine-positioning stiffness between full-step detents. **It is NOT the motor's total
torque.** The motor's **pull-out / holding torque stays roughly constant** with
microstepping — a 1/32 setting does **not** leave you with 5 % of your torque. What falls
is positional *stiffness per microstep* and the ability to reliably realize each
individual microstep against friction; below the friction threshold, fine microsteps are
"lost" (the rotor doesn't move until several accumulate). This is why microstepping buys
**smoothness/quietness, not accuracy** past ~1/8–1/16. **[snippet: EDN, Linear Motion Tips]**

### 3.3 Practical settings

- **1/16** — common default; good smoothness, manageable step rate.
- **1/32** — smoother/quieter, but pushes the **step-rate ceiling**: at 1/32 a modest joint
  speed can demand a pulse rate the controller's step generator can't sustain. TMC drivers
  mitigate via **MicroPlyer/256 interpolation** (smooth like 1/256 while the controller
  only issues 1/16 pulses).
- Balance: pick the **lowest** microstep that meets your smoothness need, to keep the
  step-rate ceiling and incremental-torque margin comfortable. For an arm, **1/16 with TMC
  interpolation** is a sound default; reserve 1/32 for low-speed, high-smoothness joints.

This choice goes straight into the **JCFG / per-joint microstep field** of the spec.

---

## 4. Power budget & PSU sizing

This is the section that is most often done wrong. Three competing "rules" exist; they
disagree by ~5×. The honest answer is to compute the **physical** draw, then size with a
**conservative** rule + margin, and understand the gap between them.

### 4.1 Why supply current ≠ Σ(phase current)

A chopper driver is effectively a **buck converter**: it chops a high supply voltage down
to whatever the low-resistance winding needs to hold rated current. At standstill/low
speed the winding only needs `V = I × R_phase` (a few volts), so **input current from the
24 V rail is far smaller than the phase current**. Power in ≈ power out:

```text
P_motor   ≈ 2 × I_phase² × R_phase           [resistive standstill power, W]  (2 phases on)
I_supply  ≈ Σ P_motor / V_supply             [steady DC draw from the rail, A]
```

NEMA17 winding resistance is ~**1–2 Ω/phase**, so at hold a 1.5 A NEMA17 dissipates only
`2 × 1.5² × ~1.3 Ω ≈ 6 W`. Six of them ≈ 35 W ⇒ **~1.5 A from 24 V at hold** — far below
the ~9 A you'd guess from `Σ phase current`. HOLD/idle current reduction lowers it further.

### 4.2 Conservative sizing rule (what to actually buy)

Standstill physics tells you the *floor*; it does **not** cover motion transients
(acceleration spikes, back-EMF, multiple joints moving), so **do not buy to the 1.5 A
floor.** Use the conservative engineering rule and add margin:

```text
P_supply ≈ n × I_rated × V_supply × k_margin      [k_margin ≈ 1.2–1.5]   (P = n·I·V·1.2 form)
I_supply = P_supply / V_supply
```

or the simpler current-sum-with-credit form **[snippet]**: `I ≈ Σ(rated phase currents) × 0.66`,
then add **30–50 % headroom**. Both are deliberately pessimistic vs §4.1 — that pessimism
*is* the transient + external-driver budget.

### 4.3 Worked generic example — 6-DOF arm

**Motors:** 6× NEMA17 @ ~1.5 A rated, 24 V, **HOLD enabled**. (If the base is NEMA23 @
2.8 A on an external DM542, add it separately — see below.)

1. **Physical hold draw (floor):** `≈ Σ P_motor / 24 V ≈ 35 W / 24 V ≈ 1.5 A`. With HOLD
   reduction, less. *This is the steady draw — it is NOT what you size the PSU to.*
2. **Conservative sizing (what to buy):** `Σ rated × V × 1.2 = 6 × 1.5 A × 24 V × 1.2 ≈
   260 W ≈ 10.8 A @ 24 V`. (The `×0.66` form gives `6 × 1.5 × 0.66 = 5.9 A`, +50 % ≈ 8.9 A
   — same ballpark.)
3. **Pick the PSU:** a **Mean Well LRS-350-24 = 14.6 A @ 24 V (350 W)** comfortably covers
   the ~9–11 A conservative figure, leaving headroom for accel transients, the controller
   logic rail, and a fan. **Honest statement: the six motors draw nowhere near 14.6 A at
   hold (~1.5 A); the LRS-350-24's headroom is for motion transients + the NEMA23 base
   joint's external driver + margin, not steady motor draw.**

**NEMA23 base joint forces an external driver:** a 2.8 A NEMA23 base exceeds the
~2 A onboard ceiling (§2) → **TB6600/DM542 fed step/dir from a spare GPIO.** Budget its
own conservative `2.8 A × 24 V × 1.2 ≈ 80 W` on top; the LRS-350-24 still absorbs it
(≈ 11 A + ~3 A ≈ 14 A — at the edge, so for a NEMA23 base consider **LRS-450-24** or a
separate rail for the base driver).

**Microstep pick for this arm:** **1/16 with TMC interpolation** as the default — keeps the
step-rate ceiling comfortable and incremental-torque margin healthy; drop the wrist/low-load
joints to 1/32 only where extra smoothness is wanted.

### 4.4 How this drives configuration

- **Driver current config:** set each `Vref` / `run_current` to **0.7–0.9 × rated phase
  current** (RMS for TMC, peak for A4988/DRV8825) — §1.
- **PSU sizing:** conservative `Σ rated × V × 1.2` + 30–50 % margin → LRS-350-24
  (LRS-450-24 if a NEMA23 base is present) — §4.2/4.3.
- **JCFG/microstep:** per-joint microstep field, default 1/16 (TMC interp), 1/32 only where
  smoothness > step-rate concern — §3.3.

---

## 5. 24 V vs 12 V — why 24 V is standard

A winding is an inductor; current rises at:

```text
di/dt = (V_supply − V_backEMF − i·R) / L      [A/s]   ≈ V_supply / L  at low speed
```

- `L` — phase inductance (H); `R` — phase resistance (Ω); `V_backEMF ∝ motor speed`.

**Higher supply voltage → faster current rise → more current actually reaches the winding
each step at speed → more high-speed torque.** At low speed both 12 V and 24 V trivially
reach rated current; at high step rates the coil has too little time to charge, and the
**higher 24 V forces current in ~2× faster**, sustaining torque to roughly double the speed.
Back-EMF (∝ speed) also opposes the supply at speed; the rule of thumb is **supply voltage
must exceed the sum of back-EMFs plus a few volts** — 24 V buys far more speed headroom than
12 V. This is why printer/arm steppers standardize on **24 V** (and why CNC external drivers
run 36–48 V). **[snippet: Duet3D, Arrow, Oyostepper]**

**Thermal / derate:** chopper drivers hold the **same RMS phase current** regardless of
12 V vs 24 V, so motor copper loss `I²R` is unchanged — but driver switching loss rises
slightly and motors run warm by design (NEMA17 surface ~50–80 °C is normal). Keep the
current limit at **70–90 % of rated** (§1) so the motor and the onboard driver stay within
thermal limits; if a motor is too hot to touch for >1 s, derate further or add cooling.
NEMA17/23 are rated to high case temps (often 80 °C class), so "warm" is expected, "hot
enough to smell" is not.

---

## Summary (engineering takeaways)

1. **Set current to the motor:** A4988 `V_ref = 8·I·R_CS` (Rsense 0.068 Ω Pololu, *peak*);
   DRV8825 `V_ref = I/2` (Rsense 0.1 Ω, *peak*); TMC `I_RMS ≈ 0.71·V_VREF` or set
   `run_current` in firmware (*RMS*). Derate to **0.7–0.9 × rated.**
2. **Onboard ≈ 2 A/phase ceiling (cooled). > ~2 A → external TB6600/DM542. NEMA17 onboard,
   NEMA23 external.**
3. **Microstepping = smoothness, not torque/accuracy.** Incremental torque `T·sin(90°/N)`
   falls (1/16→10 %, 1/32→5 %) but **total/pull-out torque ≈ constant** and current ≈ constant.
   Default **1/16 + TMC interpolation.**
4. **PSU:** size to `Σ rated × V × 1.2` + 30–50 % margin (NOT to the ~1.5 A physical hold
   floor — that gap is your transient/external-driver headroom). 6× NEMA17 @ 1.5 A, 24 V →
   ~9–11 A conservative → **Mean Well LRS-350-24 (14.6 A)** with healthy headroom
   (LRS-450-24 if a NEMA23 base is present).
5. **24 V > 12 V:** higher V → faster `di/dt = V/L` → current reaches the winding before the
   step ends → more high-speed torque; standard for arm/printer steppers.

---

## Sources

Fetched directly (primary):

- **Pololu — A4988 Stepper Motor Driver Carrier (product #1182)** —
  <https://www.pololu.com/product/1182> — `I_max = V_ref/(8·R_CS)`, R_CS = 0.068 Ω (post-2017),
  max ~1 A bare / 2 A/coil cooled. *(fetched)*
- **Pololu — DRV8825 Stepper Motor Driver Carrier, High Current (product #2133)** —
  <https://www.pololu.com/product/2133> — `I_max = 2·V_ref`, R_CS = 0.100 Ω, max ~1.5 A bare /
  2.2 A/coil cooled. *(fetched)*
- **Pololu — Video: Setting the Current Limit on Pololu Stepper Motor Driver Carriers** —
  <https://www.pololu.com/blog/484/video-setting-the-current-limit-on-pololu-stepper-motor-driver-carriers>
  — confirms per-board formula lives on the product page. *(fetched)*

Search snippets only (page not fetched / returned HTTP 403 — treat exact wording as
secondary):

- **Circuitist — How to set your stepper driver current: A4988, DRV8825, TMC2208, TMC2209** —
  <https://www.circuitist.com/how-to-set-driver-current-a4988-drv8825-tmc2208-tmc2209/> —
  A4988 `Vref = I·8·Rsense`; DRV8825 `Vref = I/2`; TMC `Vref = I·1.41`; "lower current 10–20 %."
- **OpenAstroTech Wiki — TMC2209 UART RMS Current Calculation** —
  <https://wiki.openastrotech.com/Knowledge/UART_RMS_Calculation> —
  `I_RMS = (325 mV/(R_SENSE+20 mΩ))·(1/√2)·(V_VREF/2.5 V)`. *(403 on direct fetch; snippet only)*
- **TMC2209 datasheet (Trinamic/Analog Devices), rev 1.09** —
  <https://www.analog.com/media/en/technical-documentation/data-sheets/tmc2209_datasheet_rev1.09.pdf>
  — IRUN/CS 0–31 scale, VSENSE 325 mV/180 mV, recommended IRUN 16–31. *(PDF fetch timed out;
  constants corroborated via secondary sources, not read from primary.)*
- **FYSETC / BIGTREETECH TMC2209 wikis** — <https://wiki.fysetc.com/docs/TMC2208>,
  <https://global.bttwiki.com/TMC2209.html> — R_SENSE 0.11 Ω, max 1.77 A RMS, SilentStepStick
  ~1.2 A RMS practical.
- **Minimal3DP — Run Current for TMC2208/2209 (Klipper)** —
  <https://www.minimal3dp.com/klipper-calibration/run-current/> — `run_current` is RMS;
  hold_current reduces standstill current. *(403 on direct fetch; snippet only)*
- **EDN — Why microstepping isn't as good as you think** —
  <https://www.edn.com/why-microstepping-in-stepper-motors-isnt-as-good-as-you-think/> —
  incremental torque = full-step torque × sin(90°/N); 1/8 ≈ 20 %, 1/32 ≈ 5 %; pull-out torque
  ≈ constant. *(403 on direct fetch; snippet only)*
- **Linear Motion Tips — Microstepping basics** —
  <https://www.linearmotiontips.com/microstepping-basics/> — sin(90°/N) incremental torque,
  sine/cosine phase currents, constant current magnitude. *(403 on direct fetch; snippet only)*
- **OMC StepperOnline — How to choose a power supply for my stepper motor** —
  <https://www.omc-stepperonline.com/support/how-to-choose-a-power-supply-for-my-stepper-motor>
  — manufacturer PSU sizing guidance. *(403 on direct fetch; not quoted.)*
- **Zbotic — Stepper Motor Power Supply: Choosing Voltage & Amperage** —
  <https://zbotic.in/stepper-motor-power-supply-choosing-voltage-amperage/> — `P = n·I·V·1.2`,
  30 % margin, active-vs-total current. *(403 on direct fetch; snippet only)*
- **Jim's Embeddedtronics — Stepper Motor Power Supply / Torque vs Microstepping** —
  <https://embeddedtronicsblog.wordpress.com/2021/01/22/stepper-motor-power-supply/> ,
  <https://embeddedtronicsblog.wordpress.com/2020/09/03/torque-vs-microstepping/> — PSU current
  vs Σ phase current; incremental-torque examples.
- **Duet3D — Choosing stepper motors** —
  <https://docs.duet3d.com/User_manual/Connecting_hardware/Motors_choosing> — 24 V current-rise /
  back-EMF rationale; supply > Σ back-EMF + a few volts.
- **Arrow — Stepper Motor Torque: Voltage vs Current Mode Control** —
  <https://www.arrow.com/en/research-and-events/articles/voltage-versus-current-mode-control-in-stepper-motors>
  — back-EMF ∝ speed suppresses winding current → torque falls at speed.
- **NKX Motor / eBay — TB6600** — <https://www.nkxmotor.com/shop/stepper-driver/tb6600/>;
  **Arduino Forum — NEMA23 + A4988 matching** —
  <https://forum.arduino.cc/t/stepper-motor-nema23-and-driver-a4988-matching-problem/681776> —
  TB6600 0.7–4.0 A selectable; NEMA23 ~2.8–4 A needs external driver, A4988 inadequate.

### Open uncertainties / verify-on-bench

- **R_SENSE varies by board** (A4988 clones 0.1 Ω vs Pololu 0.068 Ω; TMC boards 0.11 Ω
  typical but some 0.15 Ω). The Vref formula is exact only once you know *your* board's
  Rsense — **measure it.**
- **TMC2209 exact datasheet constants** (325/180 mV, +20 mΩ, IRUN range) are corroborated
  across secondary sources but not read from the primary PDF (fetch timed out). The
  `0.71·V_VREF` form is algebraically consistent with them.
- **NEMA17 winding resistance** (used for the ~1.5 A hold-draw floor) was taken as ~1–2 Ω/phase
  (typical); plug your motor's actual datasheet R into `P = 2·I²·R` for an exact floor.
- **NEMA23 base joint** pushes the LRS-350-24 toward its limit; bench the real combined draw
  before committing — consider LRS-450-24 or a separate rail for the base driver.
