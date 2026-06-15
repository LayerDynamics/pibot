"""Stepper robot-arm **sizing calculator** — design-time tooling (SPEC:
docs/plans/2026-06-15-stepper-arm-sizing-spec.md).

From a configurable, robot-agnostic description of an arm — per-link masses/lengths, payload,
a motor catalog, and gear options — compute, **per joint**: the worst-case required torque, the
smallest adequate ``(gear, motor)`` pair, the angular resolution, the achievable joint speed, and
the firmware ``JCFG[]`` numbers (``steps_per_deg`` / ``max_sps`` / ``accel``) — plus the arm-level
PSU current. Nothing here is robot-specific: the generic NEMA17 6-DOF baseline lives in the sample
config, not the code.

Pure stdlib (``math`` only) so the ``[ml]`` boundary stays intact — this never imports numpy. The
four domains map to the four research references in ``docs/research/stepper-arm-sizing/``:
``[A]`` gear & resolution, ``[B]`` torque & motor sizing, ``[C]`` speed/accel/step-rate,
``[D]`` driver current & power.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import NamedTuple

G_ACCEL = 9.81  # m/s^2


# ---- configuration model ---------------------------------------------------------------------


@dataclass
class MotorSpec:
    """A stepper motor in the catalog. ``holding_torque_nm`` is the datasheet standstill figure."""

    name: str  # e.g. "NEMA17-0.45"
    holding_torque_nm: float
    rated_current_a: float  # rated phase current (A)
    full_steps_per_rev: int = 200  # 200 = 1.8deg, 400 = 0.9deg
    rotor_inertia_kgm2: float = 0.0  # optional, for the inertia-match note
    max_rpm: float = 1000.0  # practical top speed before the torque-speed cliff


@dataclass
class GearOption:
    """A reduction option. ``efficiency`` is the de-rated mechanical efficiency (use real, not
    marketing). ``kind`` is informational (belt|planetary|cycloidal|worm)."""

    ratio: float  # output:motor, e.g. 50.0 for 50:1
    efficiency: float  # belt ~0.9, planetary ~0.7-0.8, worm low
    kind: str = "planetary"
    backlash_deg: float = 0.0


@dataclass
class JointConfig:
    """One joint = its motor + the link extending from it to the next joint, base->tip ordered.

    Physical fields drive the torque/inertia math; ``min/max/home`` + pin/dir fields pass straight
    through to the emitted ``JCFG[]`` row; the ``target_*`` / ``microsteps`` / ``safety_factor`` /
    ``usable_fraction`` fields are the design knobs.
    """

    name: str
    axis: str  # "horizontal" (gravity-loaded) | "vertical" (base yaw: no gravity torque)
    motor_mass_kg: float  # mass of THIS joint's actuator (sits at the joint axis)
    link_mass_kg: float  # mass of the link reaching to the next joint
    link_length_m: float
    link_com_m: float | None = None  # CG distance from this joint; None -> link_length/2

    # mechanical limits + wiring (pass-through to JCFG):
    min_deg: float = -90.0
    max_deg: float = 90.0
    home_pos_deg: float = -90.0
    step_pin: str = "PC2"
    dir_pin: str = "PB9"
    home_pin: str = "PA5"
    invert: bool = False
    home_active_low: bool = True
    home_dir: int = -1

    # design targets / knobs:
    target_speed_deg_s: float = 60.0
    target_accel_deg_s2: float = 600.0
    microsteps: int = 16
    safety_factor: float = 1.5  # SF (design margin) — kept separate from usable_fraction
    usable_fraction: float = 0.6  # u (speed derate of holding torque at the operating RPM)
    home_speed_deg_s: float = 10.0


@dataclass
class ArmSpec:
    """A whole arm + the catalogs every joint is sized against."""

    joints: list[JointConfig]  # base -> tip
    payload_kg: float
    motor_catalog: list[MotorSpec]
    gear_catalog: list[GearOption]
    supply_voltage_v: float = 24.0
    onboard_driver_limit_a: float = 2.0  # NEMA17 fits; above this -> external TB6600/DM542
    accelstepper_ceiling_sps: float = 12000.0  # polled-stepping budget on the F103 (bench-confirm)
    driver_current_fraction: float = 0.8  # set driver to this x rated phase current


# ---- [A] gear ratio & angular resolution -----------------------------------------------------


def steps_per_deg(full_steps_per_rev: int, microsteps: int, gear_ratio: float) -> float:
    """``(full_steps_per_rev * microsteps * gear_ratio) / 360`` — the firmware ``steps_per_deg``."""
    return full_steps_per_rev * microsteps * gear_ratio / 360.0


def resolution_deg(full_steps_per_rev: int, microsteps: int, gear_ratio: float) -> float:
    """Commanded angular resolution per microstep (the reciprocal of ``steps_per_deg``)."""
    return 360.0 / (full_steps_per_rev * microsteps * gear_ratio)


def fullstep_res_deg(full_steps_per_rev: int, gear_ratio: float) -> float:
    """The REAL repeatable accuracy floor — the full-step angle through the reduction (microstepping
    does not improve this)."""
    return (360.0 / full_steps_per_rev) / gear_ratio


def end_effector_arc_mm(reach_mm: float, res_deg: float) -> float:
    """Arc length (mm) that one resolution step sweeps at ``reach_mm`` from the joint."""
    return reach_mm * math.radians(res_deg)


def microstep_incremental_fraction(microsteps: int) -> float:
    """Per-microstep holding-stiffness fraction ``sin(90deg / N)`` — why fine microstepping buys
    smoothness/resolution, not load capacity."""
    return math.sin(math.radians(90.0 / microsteps))


# ---- [B] torque & motor sizing ---------------------------------------------------------------


def static_torque(distal: list[tuple[float, float]], vertical_axis: bool) -> float:
    """Worst-case gravity torque ``g * sum(m_i * d_i)`` (arm horizontal); zero for a vertical
    axis. ``distal`` = ``[(mass_kg, lever_m), ...]`` for every item beyond the joint."""
    if vertical_axis:
        return 0.0
    return G_ACCEL * sum(m * d for m, d in distal)


def joint_inertia(distal: list[tuple[float, float]]) -> float:
    """Point-mass moment of inertia about the joint axis: ``sum(m_i * d_i^2)``."""
    return sum(m * d * d for m, d in distal)


def dynamic_torque(inertia_kgm2: float, alpha_rad_s2: float) -> float:
    """Inertial torque ``I * alpha``."""
    return inertia_kgm2 * alpha_rad_s2


def joint_required_torque(t_static: float, t_dyn: float, safety_factor: float) -> float:
    """``SF * (T_static + T_dyn)`` — apply the design factor here."""
    return safety_factor * (t_static + t_dyn)


def reflect_to_motor(t_joint_nm: float, gear_ratio: float, efficiency: float) -> float:
    """Torque the motor must produce: ``T_joint / (G * eta)`` — the dominant sizing lever."""
    return t_joint_nm / (gear_ratio * efficiency)


def reflected_inertia(inertia_kgm2: float, gear_ratio: float) -> float:
    """Load inertia seen at the motor shaft: ``I_joint / G^2``."""
    return inertia_kgm2 / (gear_ratio * gear_ratio)


def motor_adequate(holding_torque_nm: float, usable_fraction: float, t_motor_req_nm: float) -> bool:
    """``T_hold * u >= T_motor_req`` — adequate at the operating speed."""
    return holding_torque_nm * usable_fraction >= t_motor_req_nm


# ---- [C] speed, acceleration & step-rate -----------------------------------------------------


def step_rate(joint_speed_deg_s: float, spd: float) -> float:
    """Step rate (steps/s) = ``joint_speed_deg_s * steps_per_deg``."""
    return joint_speed_deg_s * spd


def motor_rpm(joint_speed_deg_s: float, gear_ratio: float) -> float:
    """Motor speed (rpm) for a joint angular speed: ``joint_deg_s * G / 6``."""
    return joint_speed_deg_s * gear_ratio / 6.0


def accel_steps_s2(joint_accel_deg_s2: float, spd: float) -> float:
    """Firmware acceleration (steps/s^2) = ``joint_accel_deg_s2 * steps_per_deg``."""
    return joint_accel_deg_s2 * spd


def time_to_speed(v_max_sps: float, accel_sps2: float) -> float:
    """Trapezoidal ramp time to reach ``v_max`` at constant ``accel``."""
    return v_max_sps / accel_sps2 if accel_sps2 > 0 else math.inf


# ---- [D] driver current & power --------------------------------------------------------------


def a4988_vref(current_peak_a: float, r_sense: float = 0.068) -> float:
    """A4988 Vref ``= 8 * I_peak * R_sense`` (Pololu R_sense ~0.068; clones often 0.1)."""
    return 8.0 * current_peak_a * r_sense


def drv8825_vref(current_peak_a: float) -> float:
    """DRV8825 Vref ``= I_peak / 2`` (from ``I = Vref / (5 * 0.1ohm)``)."""
    return current_peak_a / 2.0


def tmc_vref_from_rms(i_rms_a: float) -> float:
    """TMC2208/09 ``I_RMS ~= 0.71 * Vref`` -> ``Vref = I_RMS / 0.71`` (or set run_current)."""
    return i_rms_a / 0.71


def needs_external_driver(rated_current_a: float, onboard_limit_a: float = 2.0) -> bool:
    """True if the rated phase current exceeds the onboard driver ceiling (the NEMA23 case)."""
    return rated_current_a > onboard_limit_a


def psu_current(rated_sum_a: float, transient_factor: float = 1.2, margin: float = 1.3) -> float:
    """Recommended PSU current ``sum(rated) * transient_factor * margin`` (conservative motion
    budget, not the much smaller steady hold-draw)."""
    return rated_sum_a * transient_factor * margin


# ---- results ---------------------------------------------------------------------------------


@dataclass
class JointSizing:
    """The computed sizing for one joint."""

    name: str
    axis: str
    t_static_nm: float
    t_dyn_nm: float
    t_joint_req_nm: float
    motor: MotorSpec
    gear: GearOption
    t_motor_req_nm: float
    torque_margin: float  # holding*u / t_motor_req (>=1 is a pass)
    reflected_inertia_kgm2: float
    microsteps: int
    steps_per_deg: float
    resolution_deg: float
    fullstep_res_deg: float
    end_effector_arc_mm: float
    target_speed_deg_s: float
    achievable_speed_deg_s: float  # after the step-rate ceiling cap
    max_sps: int  # firmware JCFG max_sps (capped at the polled ceiling)
    accel_sps2: int  # firmware JCFG accel
    home_sps: int  # firmware JCFG home_sps
    motor_rpm: float
    driver_current_a: float  # set driver current (= fraction * rated)
    needs_external_driver: bool
    adequate: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class ArmSizing:
    """The computed sizing for the whole arm."""

    joints: list[JointSizing]
    reach_m: float
    total_rated_current_a: float
    recommended_psu_current_a: float
    supply_voltage_v: float
    joints_needing_external_driver: list[str]
    all_adequate: bool


class _Candidate(NamedTuple):
    """One ``(motor, gear)`` option evaluated for a joint."""

    motor: MotorSpec
    gear: GearOption
    steps_per_deg: float
    t_motor_req: float
    step_rate: float
    motor_rpm: float
    torque_ok: bool  # holding*u >= required motor torque
    speed_ok: bool  # target speed stays under the polled step-rate ceiling (and motor max rpm)


# ---- geometry: the distal mass table ---------------------------------------------------------


def distal_masses(arm: ArmSpec, joint_index: int) -> list[tuple[float, float]]:
    """Every mass DISTAL to ``joint_index``, as ``(mass_kg, horizontal_lever_m)`` measured from that
    joint with the arm fully extended horizontally. Joint ``j``'s own motor is at the axis (lever 0,
    excluded). Each joint's table is a superset of the joint above it.
    """
    items: list[tuple[float, float]] = []
    cum = 0.0  # distance from joint_index along the (extended) arm
    for k in range(joint_index, len(arm.joints)):
        seg = arm.joints[k]
        if k > joint_index:
            # the actuator at joint k sits at the proximal end of segment k
            items.append((seg.motor_mass_kg, cum))
        com = seg.link_com_m if seg.link_com_m is not None else seg.link_length_m / 2.0
        items.append((seg.link_mass_kg, cum + com))
        cum += seg.link_length_m
    items.append((arm.payload_kg, cum))  # payload at the tip
    return items


def arm_reach_m(arm: ArmSpec) -> float:
    """Total reach = sum of link lengths (base -> tip)."""
    return sum(j.link_length_m for j in arm.joints)


# ---- the sizing engine -----------------------------------------------------------------------


def size_joint(arm: ArmSpec, joint_index: int) -> JointSizing:
    """Size one joint: compute worst-case torque, then pick the smallest adequate ``(motor, gear)``
    that also meets the speed/step-rate budget, and derive the firmware numbers.
    """
    jc = arm.joints[joint_index]
    distal = distal_masses(arm, joint_index)
    vertical = jc.axis == "vertical"

    t_static = static_torque(distal, vertical)
    inertia = joint_inertia(distal)
    t_dyn = dynamic_torque(inertia, math.radians(jc.target_accel_deg_s2))
    t_joint_req = joint_required_torque(t_static, t_dyn, jc.safety_factor)

    reach_to_tip = sum(j.link_length_m for j in arm.joints[joint_index:])

    # Evaluate every (motor, gear): torque-OK, and does it keep the target speed under the ceiling?
    candidates: list[_Candidate] = []
    for motor_opt in arm.motor_catalog:
        for gear_opt in arm.gear_catalog:
            spd_c = steps_per_deg(motor_opt.full_steps_per_rev, jc.microsteps, gear_opt.ratio)
            tmr = reflect_to_motor(t_joint_req, gear_opt.ratio, gear_opt.efficiency)
            sr_c = step_rate(jc.target_speed_deg_s, spd_c)
            rpm_c = motor_rpm(jc.target_speed_deg_s, gear_opt.ratio)
            candidates.append(
                _Candidate(
                    motor=motor_opt,
                    gear=gear_opt,
                    steps_per_deg=spd_c,
                    t_motor_req=tmr,
                    step_rate=sr_c,
                    motor_rpm=rpm_c,
                    torque_ok=motor_adequate(motor_opt.holding_torque_nm, jc.usable_fraction, tmr),
                    speed_ok=sr_c <= arm.accelstepper_ceiling_sps and rpm_c <= motor_opt.max_rpm,
                )
            )

    notes: list[str] = []
    valids = [c for c in candidates if c.torque_ok and c.speed_ok]
    torque_oks = [c for c in candidates if c.torque_ok]  # torque covered (speed may be capped)
    if valids:
        # smallest motor frame (lowest holding torque), then smallest gear (fastest joint).
        chosen = min(valids, key=lambda c: (c.motor.holding_torque_nm, c.gear.ratio))
        adequate = True
    elif torque_oks:
        # Torque is covered, but no gear keeps the TARGET speed under the polled step-rate ceiling.
        # Pick the smallest motor + smallest gear (lowest step rate -> best achievable speed): the
        # joint IS adequately sized, it just runs slower than asked (the cap is noted below).
        chosen = min(torque_oks, key=lambda c: (c.motor.holding_torque_nm, c.gear.ratio))
        adequate = True
    else:
        # Nothing covers the torque budget — show the closest by torque headroom and flag it.
        chosen = max(
            candidates,
            key=lambda c: c.motor.holding_torque_nm * jc.usable_fraction - c.t_motor_req,
        )
        adequate = False
        notes.append(
            "no motor+gear meets the torque budget — raise gear ratio, step up motor frame, "
            "lower payload/reach, or relax SF/u"
        )

    motor, gear, spd = chosen.motor, chosen.gear, chosen.steps_per_deg
    t_motor_req, sr, rpm = chosen.t_motor_req, chosen.step_rate, chosen.motor_rpm

    capped_sr = min(sr, arm.accelstepper_ceiling_sps)
    if sr > arm.accelstepper_ceiling_sps:
        notes.append(
            f"target {jc.target_speed_deg_s:.0f} deg/s needs {sr:.0f} sps > ceiling "
            f"{arm.accelstepper_ceiling_sps:.0f}; capped (achievable "
            f"{capped_sr / spd:.0f} deg/s)"
        )
    holding_budget = motor.holding_torque_nm * jc.usable_fraction
    margin = holding_budget / t_motor_req if t_motor_req > 0 else math.inf

    return JointSizing(
        name=jc.name,
        axis=jc.axis,
        t_static_nm=t_static,
        t_dyn_nm=t_dyn,
        t_joint_req_nm=t_joint_req,
        motor=motor,
        gear=gear,
        t_motor_req_nm=t_motor_req,
        torque_margin=margin,
        reflected_inertia_kgm2=reflected_inertia(inertia, gear.ratio),
        microsteps=jc.microsteps,
        steps_per_deg=spd,
        resolution_deg=resolution_deg(motor.full_steps_per_rev, jc.microsteps, gear.ratio),
        fullstep_res_deg=fullstep_res_deg(motor.full_steps_per_rev, gear.ratio),
        end_effector_arc_mm=end_effector_arc_mm(
            reach_to_tip * 1000.0,
            resolution_deg(motor.full_steps_per_rev, jc.microsteps, gear.ratio),
        ),
        target_speed_deg_s=jc.target_speed_deg_s,
        achievable_speed_deg_s=capped_sr / spd,
        max_sps=round(capped_sr),
        accel_sps2=round(accel_steps_s2(jc.target_accel_deg_s2, spd)),
        home_sps=round(step_rate(jc.home_speed_deg_s, spd)),
        motor_rpm=rpm,
        driver_current_a=motor.rated_current_a * arm.driver_current_fraction,
        needs_external_driver=needs_external_driver(
            motor.rated_current_a, arm.onboard_driver_limit_a
        ),
        adequate=adequate,
        notes=notes,
    )


def size_arm(arm: ArmSpec) -> ArmSizing:
    """Size every joint and aggregate the arm-level PSU + external-driver summary."""
    joints = [size_joint(arm, i) for i in range(len(arm.joints))]
    rated_sum = sum(j.motor.rated_current_a for j in joints)
    return ArmSizing(
        joints=joints,
        reach_m=arm_reach_m(arm),
        total_rated_current_a=rated_sum,
        recommended_psu_current_a=psu_current(rated_sum),
        supply_voltage_v=arm.supply_voltage_v,
        joints_needing_external_driver=[j.name for j in joints if j.needs_external_driver],
        all_adequate=all(j.adequate for j in joints),
    )


# ---- config loading + reporting (CLI) --------------------------------------------------------


def load_arm_toml(path: str) -> ArmSpec:
    """Load an :class:`ArmSpec` from a TOML file: an ``[arm]`` scalar table plus ``[[motor]]``,
    ``[[gear]]``, and base->tip ``[[joint]]`` array-of-tables."""
    import tomllib

    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    arm_cfg = dict(data.get("arm", {}))
    motors = [MotorSpec(**m) for m in data["motor"]]
    gears = [GearOption(**g) for g in data["gear"]]
    joints = [JointConfig(**j) for j in data["joint"]]
    return ArmSpec(joints=joints, motor_catalog=motors, gear_catalog=gears, **arm_cfg)


def jcfg_row(jc: JointConfig, js: JointSizing) -> str:
    """Render one firmware ``JCFG[]`` row from a joint's config (pins/limits) + computed sizing."""
    cells = [
        f"{jc.step_pin},",
        f"{jc.dir_pin},",
        f"{jc.home_pin},",
        f"{'true' if jc.invert else 'false'},",
        f"{'true' if jc.home_active_low else 'false'},",
        f"{jc.home_dir},",
        f"{js.steps_per_deg:.3f}f,",
        f"{jc.min_deg:.0f}.f,",
        f"{jc.max_deg:.0f}.f,",
        f"{jc.home_pos_deg:.0f}.f,",
        f"{js.max_sps}.f,",
        f"{js.accel_sps2}.f,",
        f"{js.home_sps}.f",
    ]
    return "  { " + " ".join(cells) + " }, // " + js.name


def format_jcfg_block(arm: ArmSpec, sizing: ArmSizing) -> str:
    """The copy-pasteable ``JCFG[]`` block for firmware/pibot_arm_stm32."""
    header = (
        "static const JointCfg JCFG[] = {\n"
        "  // step dir home  inv   hlow  hdir  s/deg      min    max   homepos  maxsps  "
        "accel   homesps"
    )
    rows = [jcfg_row(jc, js) for jc, js in zip(arm.joints, sizing.joints, strict=True)]
    return header + "\n" + "\n".join(rows) + "\n};"


def format_report(arm: ArmSpec, sizing: ArmSizing) -> str:
    """A human-readable per-joint sizing report + arm-level PSU/driver summary + the JCFG block."""
    lines: list[str] = []
    lines.append(
        f"Arm reach {sizing.reach_m * 1000:.0f} mm, payload {arm.payload_kg:.2f} kg, "
        f"{arm.supply_voltage_v:.0f} V"
    )
    lines.append("")
    for js in sizing.joints:
        flag = "OK" if js.adequate else "** UNDER-SIZED **"
        lines.append(f"[{js.name}]  ({js.axis} axis)  {flag}")
        lines.append(
            f"  torque: static {js.t_static_nm:.2f} + dyn {js.t_dyn_nm:.2f} "
            f"-> req {js.t_joint_req_nm:.2f} N·m (SF applied)"
        )
        lines.append(
            f"  motor : {js.motor.name} @ {js.gear.ratio:.0f}:1 {js.gear.kind} "
            f"(η{js.gear.efficiency:.2f}) -> needs {js.t_motor_req_nm:.3f} N·m, "
            f"margin ×{js.torque_margin:.2f}"
        )
        lines.append(
            f"  motion: {js.steps_per_deg:.2f} steps/deg, res {js.resolution_deg:.4f}° "
            f"(full-step floor {js.fullstep_res_deg:.3f}°, ~{js.end_effector_arc_mm:.2f} mm @ tip)"
        )
        lines.append(
            f"          speed {js.achievable_speed_deg_s:.0f} deg/s "
            f"({js.motor_rpm:.0f} rpm), max_sps {js.max_sps}, accel {js.accel_sps2}"
        )
        lines.append(
            f"  driver: set {js.driver_current_a:.2f} A"
            + ("  ** external driver (>onboard limit) **" if js.needs_external_driver else "")
        )
        for note in js.notes:
            lines.append(f"  ! {note}")
        lines.append("")
    ext = sizing.joints_needing_external_driver
    lines.append(
        f"PSU: {sizing.total_rated_current_a:.1f} A rated total -> recommend "
        f"≥ {sizing.recommended_psu_current_a:.1f} A @ {sizing.supply_voltage_v:.0f} V"
    )
    if ext:
        lines.append(f"External drivers required for: {', '.join(ext)}")
    lines.append(
        "All joints adequately sized."
        if sizing.all_adequate
        else "Some joints are under-sized — see flags above."
    )
    lines.append("")
    lines.append(
        "--- firmware JCFG[] (pins/limits from config; steps_per_deg/max_sps/accel computed) ---"
    )
    lines.append(format_jcfg_block(arm, sizing))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """``python -m pibot.arm.sizing <config.toml>`` — size an arm and print the report + JCFG."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="pibot.arm.sizing",
        description="Size a stepper robot arm and emit the firmware JCFG[] numbers.",
    )
    parser.add_argument("config", help="path to an arm TOML config (see examples/)")
    args = parser.parse_args(argv)

    arm = load_arm_toml(args.config)
    sizing = size_arm(arm)
    print(format_report(arm, sizing))
    return 0 if sizing.all_adequate else 1


if __name__ == "__main__":
    raise SystemExit(main())
