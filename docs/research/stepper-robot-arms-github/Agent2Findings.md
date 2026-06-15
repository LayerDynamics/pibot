# Agent 2 Findings — Controllers, Firmware & Stepper-Driver Hardware

**Facet:** For each open-source stepper robot arm, what controller/board it runs, what
firmware stack and host wire protocol it uses, its stepper axis/driver count and driver
type (step/dir vs closed-loop CAN), and **whether it maps onto a Creality 4.2.2-class
STM32F103 board** (4 onboard step/dir drivers, no FPU, 72 MHz, ~1.5–2 A/driver ceiling,
24 V) running PiBot's AccelStepper-style ASCII-line+CRC firmware.

> **Sourcing discipline:** Every board/firmware claim below was checked against the
> project's own repo/docs/wiki (see `Agent2Sources.md`). Where a primary source could not
> be reached, the cell is marked **unverified**.

---

## The compatibility rubric (three axes, not two)

The briefing's binary (driver count + closed-loop) misses motor current. A board can speak
step/dir and still be wrong if the motor draws more current than its onboard driver can
source. So each arm is judged on:

1. **Driver paradigm** — step/dir (A4988 / DRV8825 / TMC2208/2209) vs **closed-loop CAN
   servo** (MKS SERVO, custom Ctrl-Step) vs **custom PCB**. Step/dir is what a 4.2.2's
   onboard drivers *are*; CAN/closed-loop and custom PCBs are a different controller class
   entirely and do **not** port.
2. **Driver count vs the 4 onboard** (X/Y/Z/E). 5–6 DOF > 4 ⇒ needs a 2nd 4.2.2, a driver
   expansion, or a board with more sockets.
3. **Motor current / size** — **NEMA 17** (≤ ~2 A, onboard A4988/TMC2208 OK) vs **NEMA 23**
   (often 3 A, needs an **external** TB6600/DM542-class driver even though it's still
   step/dir). This is exactly what makes Moveo "Adaptable" not "Direct."

**Verdict scale**
- **Direct fit** — step/dir, ≤4 NEMA17 axes, runs on one 4.2.2 with PiBot firmware as-is.
- **Adaptable** — step/dir, but needs a 2nd board (for >4 drivers) and/or external
  high-current drivers (NEMA23). The control *model* matches; the hardware count/current
  doesn't fit one bare 4.2.2.
- **Hard** — mandates a different controller class: Teensy 4.x, closed-loop CAN servos, or
  a bespoke per-motor PCB. PiBot's firmware/board model doesn't apply without a rewrite.

---

## Per-project controller / firmware table

| Arm | Controller board | Firmware stack | Host protocol | Stepper axes & drivers | Driver paradigm / motors | **4.2.2 verdict** |
|---|---|---|---|---|---|---|
| **BCN3D Moveo** | Arduino Mega 2560 + **RAMPS 1.4** (board confirmed via the RAMPS-pinned `FIRMWARE/Marlin_BCN3D_Moveo` config + BOM; the repo README does not name the board in prose) | **Marlin** (3D-printer firmware, repurposed) | **G-code** over USB serial | 5 DOF; ~5–6 stepper outputs (one joint dual-motor on a RAMPS dual-Z socket) + 1 servo gripper | **step/dir**, but mixed **NEMA 23 (3 A, e.g. SM57HT112) + NEMA 17**. Heavy joints exceed 4.2.2 onboard driver current. | **Adaptable** — needs a 2nd board (>4 drivers) **and** external TB6600/DM542 drivers for the NEMA23s; can't run off one bare 4.2.2's onboard drivers. Control model (step/dir + endstops + soft limits) maps cleanly. |
| **Annin AR2** | **Arduino Mega 2560** (open-loop, no coprocessor) | Custom Arduino sketch + Python host GUI | Custom **ASCII serial** over USB | 6 stepper axes driving **external DM-series drivers** | **step/dir** to external drivers; NEMA17/23-class, **no encoders** | **Adaptable — friendliest of the Annin line.** Pure open-loop step/dir + ASCII serial is the closest match to PiBot's model. Still 6 drivers ⇒ 2nd 4.2.2, and it expects **external** drivers (so onboard-current limits are moot — you'd feed external drivers step/dir from GPIO). No Teensy, no encoders. |
| **Annin AR3** | **Teensy 3.5** (motors + encoders) **+ Arduino Mega** (I/O, gripper, servos) | Custom Teensy + Mega sketches; Python host | Custom **ASCII serial** | 6 stepper axes + **encoders (closed-loop)**, external **DM542T** drivers | **step/dir to external DM542T + encoders** | **Hard (leaning Adaptable-if-stripped).** As designed it mandates the **Teensy 3.5 coprocessor for encoder closed-loop**; that doesn't move onto a 4.2.2. Drop the encoders (run open-loop like AR2) and it becomes Adaptable, but then it's effectively AR2. |
| **PAROL6 (Source Robotics)** | **Custom board: STM32F446RE** (Cortex-M4, **has FPU**) + **TMC5160** drivers on-board, CAN, ESTOP, 64MB flash | Custom STM32 firmware (TMCStepper lib) | USB serial; PAROL commander GUI / Python API | 6 on-board TMC5160 step/dir drivers + 6 limit sensors | **step/dir** (TMC5160, on a bespoke PCB) | **Hard** — it already *is* a purpose-built STM32 arm controller (more capable than a 4.2.2: 6 on-board drivers, FPU, CAN). No reason to port to a 4.2.2; included as the "what a dedicated STM32 arm board looks like" reference point. Control model is step/dir, so conceptually aligned. |
| **Thor (AngelLM)** | Arduino Mega + **custom RAMPS-1.4-based shield** ("ThorControlPCB", up to 8 A4988 sockets) | **modified GRBL** | **G-code** over serial | 6 DOF but **dual-motor articulations ⇒ ~7 A4988 drivers** | **step/dir** A4988; NEMA17-class | **Adaptable** — step/dir model fits PiBot firmware, but **7 drivers needs a 2nd 4.2.2** (4+4). No closed-loop/CAN, so electrically the friendliest of the "needs 2 boards" arms. |
| **Arctos (original / open-loop)** | **Arduino Mega 2560 + CNC Shield V3** with A4988/DRV8825 (Hackaday-verified original); current docs also offer Mega + CNC-shield TMC2209 | **modified GRBL** (6-axis) | **G-code** | 6 DOF; 6 step/dir + optional encoders | **step/dir** A4988/DRV8825/TMC2209; mixed **NEMA 23 (X/Y) + NEMA 17** | **Adaptable** (open-loop build only) — step/dir matches, but 6 drivers ⇒ 2nd board, and NEMA23 joints ⇒ external drivers. |
| **Arctos (current / recommended closed-loop)** | **CANable v2 USB-CAN** → **MKS SERVO42D ×4 + SERVO57D ×2** (per-motor closed-loop drivers); no central step/dir controller | **MKS** servo firmware per motor; ROS1/ROS2 + GUI host-side | **CAN bus** (+ ROS) | 6 closed-loop servo-steppers, drivers integrated per motor | **closed-loop CAN servo** | **Hard** — this configuration has no central step/dir board at all; a 4.2.2 cannot drive MKS-over-CAN with AccelStepper. Different controller class entirely. |
| **Annin AR4 / AR4-MK3** | **Teensy 4.1** (600 MHz Cortex-**M7, has FPU**) + Arduino Nano (gripper) — verified repo/README | Custom **Teensy sketch** (`annin_ar4_firmware`); ROS 2 driver host-side | Custom **ASCII serial** over USB (pyserial); also ROS 2 | 6 stepper axes + **per-joint encoders (closed-loop calibration/homing)** | step/dir to external drivers **+ encoders**; needs the Teensy's pin count & speed | **Hard** — design assumes Teensy 4.1 (encoders, 600 MHz). The 72 MHz no-FPU F103 + 4 onboard drivers can't host AR4's encoder-closed-loop firmware as-is. Control model (per-joint pos, homing) is conceptually close, but the board mandate is not portable. |
| **peng-zhihui Dummy Robot** | **Custom**: STM32F4 main controller + ESP32 (Wi-Fi) + **custom per-motor closed-loop "Ctrl-Step" driver (STM32F1, FOC) over CAN** | Custom STM32F4 firmware (FreeRTOS) + per-motor Ctrl-Step firmware | **CAN** (motor) + custom serial/Wi-Fi (host) | 6–7 joints; each motor has its own integrated closed-loop driver | **custom closed-loop CAN** (harmonic-drive steppers) | **Hard** — bespoke distributed CAN/FOC architecture; nothing maps onto a single step/dir 4.2.2. |
| **EEZYbotARM (MK2/MK3)** | Arduino Uno/Nano/ESP32 (community) | Arduino sketch (servo PWM) | Custom **serial** (ASCII) | **Servo-driven, not stepper** (MG996R-class); community CNC-shield stepper mod exists | hobby **servos** (PWM), not steppers | **Out of scope / N/A** — it's a *servo* arm. The 4.2.2's stepper drivers are the wrong actuator interface; only a non-standard stepper retrofit would even apply. |
| **WLkata Mirobot** | Closed commercial controller (**STM32-class**, unverified internals) | Proprietary GRBL-derived firmware | **G-code** over serial; Python/ROS2 SDK | 6 DOF (integrated steppers) | proprietary; **not open hardware** | **Hard / N/A** — firmware & board are closed; you can't reflash a 4.2.2 to be a Mirobot. Listed for completeness; the *protocol* (G-code) is the only reusable idea. |

---

## "Can a 3D-printer STM32 board drive a 6-DOF arm?" — analysis

**Short answer:** Yes for the *step generation*, with two real caveats — **driver count** and
**motor current** — and **CPU is not the bottleneck** in PiBot's architecture.

### 1. The F103 CPU is *not* the limiting factor (the driver count is)
The tightest constraint is **hardware**, not compute. Reasons:

- **IK runs host-side.** In PiBot's design the solver seam (ikpy/DH/URDF) runs on the
  Raspberry Pi, and the 4.2.2 only receives per-joint position/velocity and emits
  **step/dir**. So "no FPU / 72 MHz" is largely a non-issue — the MCU never does
  trig/matrix kinematics. (This is the opposite of AR4/Dummy, which push closed-loop logic
  onto the controller.)
- **Step-rate headroom is ample.** Empirically, **grblHAL on an STM32F103** sustains
  **~250 kHz/axis for 3-axis coordinated motion and ~150 kHz/axis at 6 axes** — an order of
  magnitude above 8-bit AVR. A robot joint stepping at, say, 5–20 kHz is far under that
  ceiling. The F103 has the timer/interrupt budget to bit-bang or timer-drive 4 step/dir
  channels comfortably.
- **AccelStepper caveat (library, not silicon):** classic `AccelStepper` tops out around
  ~4 kSteps/s on a 16 MHz AVR and **`MultiStepper` does constant-speed-only (no
  accel/decel) coordinated moves**. On an STM32 the same library reaches ~30–100 kSteps/s.
  For smooth multi-axis ramps PiBot's firmware should drive steps from a hardware
  timer/ISR (as grblHAL/Marlin do) rather than lean on `AccelStepper::run()` loop polling —
  but that's a firmware-design choice, not an F103 limit.

### 2. The two constraints that *do* bite
- **Only 4 onboard drivers.** Every 5–6 DOF arm needs **5–7 drivers**, so a single 4.2.2 is
  short by 1–3. Options: a **2nd 4.2.2** (4+4 = 8 channels, matches Thor/Moveo/Arctos), a
  board with more sockets (BTT Octopus = 8, SKR), or external driver modules off spare GPIO.
- **Onboard driver current.** A 4.2.2's onboard A4988/TMC2208-class drivers source ~1.2–2 A
  — fine for **NEMA17**, **not** for the **NEMA 23 (3 A)** base/shoulder joints on Moveo and
  Arctos. Those joints need **external TB6600/DM542** drivers fed step/dir from the board's
  GPIO (still compatible, just not "onboard").

### 3. Precedent: people *do* run multi-axis arms on printer-class boards
- **grblHAL** explicitly supports up to **6 axes** on STM32 (incl. F103/F4) and lists many
  3D-printer/CNC boards as targets — this is the most direct "printer board → 6-axis arm"
  path and uses the same **step/dir** model PiBot already speaks.
- **Klipper** community mods extend XYZ→XYZABC (6-axis) on printer MCUs (FYSETC Spider/SKR),
  though 6-axis is a community patch, not core.
- **Marlin** is the Moveo/Arctos precedent (G-code arm on Mega+RAMPS); a 4.2.2 is just the
  STM32 successor to that AVR board.

### 4. What this means for PiBot specifically
- **Most controller-compatible arms** are the **open-loop step/dir arms** — **Annin AR2**,
  **Thor**, **Moveo**, and **open-loop Arctos**. Their control model (per-joint step/dir,
  endstop homing, soft limits, e-stop) is exactly PiBot's firmware model. **AR2 is the single
  best fit** of the named set: it's already open-loop, already uses external step/dir drivers,
  and already speaks a custom **ASCII serial** link (not G-code) — so it needs only a 2nd
  4.2.2 for the 5th/6th driver, with no protocol shim and no current-ceiling worry (external
  drivers). Thor/Moveo/open-loop-Arctos are next: same step/dir model, but need a **2nd 4.2.2**
  for the 5th–7th driver, **external high-current drivers** for NEMA23 joints, and a host-side
  **G-code → ASCII-line+CRC** shim.
- **Hardest** are the arms that mandate a **different controller class**: **AR4** (Teensy 4.1
  + encoders), **AR3** (Teensy 3.5 coprocessor for encoder closed-loop), **Dummy** and
  **closed-loop Arctos** (custom/MKS closed-loop CAN servos), **PAROL6** (its own bespoke
  STM32F446 + TMC5160 board), and **Mirobot** (closed hardware). These can't be hosted on a
  4.2.2 with AccelStepper-style firmware without abandoning their core electronics.
- **EEZYbotARM** is a **servo** arm — wrong actuator class for a stepper board.

**Bottom line:** A Creality 4.2.2 is a legitimate stepper controller for a sub-4-DOF
step/dir NEMA17 arm out of the box, and for a 5–7 DOF NEMA17/23 arm (Thor/Moveo/open-loop
Arctos) with a 2nd board + external drivers for the big joints. The F103's lack of FPU /
72 MHz clock is a red herring because kinematics lives on the Pi; the real limits are the
4-driver count and the onboard current ceiling.
