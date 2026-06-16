"""Tests for the stepper-arm sizing calculator (pibot/arm/sizing.py).

The numeric assertions are the arithmetic-verified worked examples from the research
(docs/research/stepper-arm-sizing/), so a regression in any formula trips here.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from pibot.arm import sizing as s

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "arm-generic-6dof.toml"

# The research's worked-example shoulder distal mass table: (mass_kg, horizontal_lever_m).
SHOULDER_DISTAL = [(0.40, 0.13), (0.30, 0.25), (0.30, 0.40), (0.30, 0.50), (0.50, 0.55)]


# ---- [A] gear & resolution -------------------------------------------------------------------


def test_steps_per_deg_worked() -> None:
    assert s.steps_per_deg(200, 16, 5) == pytest.approx(44.444, abs=1e-3)
    # rearrangement: resolution is the reciprocal
    assert s.resolution_deg(200, 16, 5) == pytest.approx(1 / 44.444, abs=1e-5)


def test_resolution_vs_fullstep_floor() -> None:
    # 200, 16us, 5:1 -> commanded 0.0225 deg, but the REAL full-step floor is 0.36 deg.
    assert s.resolution_deg(200, 16, 5) == pytest.approx(0.0225, abs=1e-4)
    assert s.fullstep_res_deg(200, 5) == pytest.approx(0.36, abs=1e-4)
    # doubling the RATIO halves the real floor; doubling MICROSTEPS does not.
    assert s.fullstep_res_deg(200, 10) == pytest.approx(0.18, abs=1e-4)
    assert s.fullstep_res_deg(200, 5) == s.fullstep_res_deg(200, 5)  # microsteps absent by design


def test_microstep_incremental_fraction() -> None:
    # T_inc ≈ T_hold * sin(90/N): N=8 -> ~0.195, N=16 -> ~0.098 (smoothness, not load capacity).
    assert s.microstep_incremental_fraction(8) == pytest.approx(0.195, abs=1e-3)
    assert s.microstep_incremental_fraction(16) == pytest.approx(0.098, abs=1e-3)


def test_end_effector_arc() -> None:
    assert s.end_effector_arc_mm(1000.0, 0.0225) == pytest.approx(0.3927, abs=1e-3)


# ---- [B] torque & motor sizing ---------------------------------------------------------------


def test_static_torque_shoulder_worked() -> None:
    assert s.static_torque(SHOULDER_DISTAL, vertical_axis=False) == pytest.approx(6.59, abs=0.02)


def test_static_torque_zero_for_vertical_axis() -> None:
    assert s.static_torque(SHOULDER_DISTAL, vertical_axis=True) == 0.0


def test_inertia_and_dynamic_torque_worked() -> None:
    inertia = s.joint_inertia(SHOULDER_DISTAL)
    assert inertia == pytest.approx(0.300, abs=0.002)
    assert s.dynamic_torque(inertia, 2.0) == pytest.approx(0.60, abs=0.01)


def test_joint_required_and_reflect_to_motor_worked() -> None:
    t_static = s.static_torque(SHOULDER_DISTAL, vertical_axis=False)
    t_dyn = s.dynamic_torque(s.joint_inertia(SHOULDER_DISTAL), 2.0)
    t_joint = s.joint_required_torque(t_static, t_dyn, 1.5)
    assert t_joint == pytest.approx(10.8, abs=0.1)
    # 50:1, eta 0.8 -> 0.27 N·m (NEMA17 territory); 20:1 -> 0.67 (forces NEMA23).
    assert s.reflect_to_motor(t_joint, 50, 0.8) == pytest.approx(0.27, abs=0.01)
    assert s.reflect_to_motor(t_joint, 20, 0.8) == pytest.approx(0.67, abs=0.01)


def test_motor_adequate_thresholds() -> None:
    # NEMA17 0.45 N·m at u=0.6 -> budget 0.27; clears 0.27 but not 0.67.
    assert s.motor_adequate(0.45, 0.6, 0.27) is True
    assert s.motor_adequate(0.45, 0.6, 0.67) is False
    # NEMA23 1.9 at u=0.6 -> budget 1.14; clears 0.67.
    assert s.motor_adequate(1.9, 0.6, 0.67) is True


def test_reflected_inertia() -> None:
    assert s.reflected_inertia(0.300, 50) == pytest.approx(0.300 / 2500, abs=1e-7)


# ---- [C] speed, accel & step-rate ------------------------------------------------------------


def test_step_rate_and_motor_rpm_worked() -> None:
    spd = s.steps_per_deg(200, 16, 5)
    assert s.step_rate(60.0, spd) == pytest.approx(2667, abs=1)
    assert s.motor_rpm(60.0, 5) == pytest.approx(50.0, abs=1e-6)


def test_accel_and_time_to_speed_worked() -> None:
    spd = s.steps_per_deg(200, 16, 5)
    accel = s.accel_steps_s2(600.0, spd)
    assert accel == pytest.approx(26667, abs=2)
    assert s.time_to_speed(s.step_rate(60.0, spd), accel) == pytest.approx(0.10, abs=0.005)


def test_time_to_speed_zero_accel() -> None:
    assert s.time_to_speed(1000.0, 0.0) == math.inf


# ---- [D] driver current & power --------------------------------------------------------------


def test_driver_vref_formulas() -> None:
    assert s.a4988_vref(1.5) == pytest.approx(0.816, abs=1e-3)  # 8 * 1.5 * 0.068
    assert s.drv8825_vref(1.5) == pytest.approx(0.75, abs=1e-6)  # I / 2
    assert s.tmc_vref_from_rms(1.2) == pytest.approx(1.2 / 0.71, abs=1e-3)


def test_external_driver_threshold() -> None:
    assert s.needs_external_driver(1.5, 2.0) is False  # NEMA17 onboard
    assert s.needs_external_driver(2.8, 2.0) is True  # NEMA23 -> external


def test_psu_current_rule() -> None:
    # 6x NEMA17 @ 1.5 A -> 9 A rated; *1.2 transient *1.3 margin = 14.04 A.
    assert s.psu_current(9.0) == pytest.approx(14.04, abs=0.01)


# ---- geometry: the distal mass table ---------------------------------------------------------


def _two_joint_arm() -> s.ArmSpec:
    motors = [s.MotorSpec("NEMA17", 0.45, 1.5), s.MotorSpec("NEMA23", 1.9, 2.8)]
    gears = [s.GearOption(10, 0.9, "belt"), s.GearOption(50, 0.75, "planetary")]
    j0 = s.JointConfig("base", "vertical", motor_mass_kg=0.4, link_mass_kg=0.0, link_length_m=0.10)
    j1 = s.JointConfig(
        "shoulder",
        "horizontal",
        motor_mass_kg=0.3,
        link_mass_kg=0.2,
        link_length_m=0.30,
        link_com_m=0.15,
    )
    return s.ArmSpec(joints=[j0, j1], payload_kg=0.5, motor_catalog=motors, gear_catalog=gears)


def test_distal_masses_levers() -> None:
    arm = _two_joint_arm()
    # From the shoulder (index 1): own motor excluded; link CG at 0.15; payload at tip 0.30.
    distal = s.distal_masses(arm, 1)
    assert (0.2, 0.15) in distal  # shoulder link mass at its CG
    assert (0.5, 0.30) in distal  # payload at the tip of the shoulder link
    # From the base (index 0): base link length 0.10, so the shoulder motor sits at lever 0.10.
    base = s.distal_masses(arm, 0)
    assert (0.3, 0.10) in base  # shoulder motor distal to the base
    assert s.arm_reach_m(arm) == pytest.approx(0.40, abs=1e-9)


# ---- size_joint / size_arm -------------------------------------------------------------------


def test_size_joint_vertical_has_zero_static() -> None:
    arm = _two_joint_arm()
    js = s.size_joint(arm, 0)
    assert js.t_static_nm == 0.0  # vertical base axis: no gravity torque
    assert js.t_dyn_nm > 0.0  # but inertia/accel still load it
    assert js.adequate is True


def test_size_joint_picks_smallest_adequate_motor() -> None:
    arm = _two_joint_arm()
    js = s.size_joint(arm, 1)  # shoulder
    assert js.adequate is True
    assert js.t_joint_req_nm > 0.0
    assert js.steps_per_deg > 0.0
    assert js.max_sps > 0


def test_size_joint_undersized_when_no_motor_fits() -> None:
    # A brutally heavy joint with only a weak motor + low gear -> nothing covers torque.
    weak = [s.MotorSpec("tiny", 0.1, 0.5)]
    low = [s.GearOption(2, 0.9, "belt")]
    heavy = s.JointConfig(
        "big", "horizontal", motor_mass_kg=5.0, link_mass_kg=5.0, link_length_m=1.0
    )
    arm = s.ArmSpec(joints=[heavy], payload_kg=5.0, motor_catalog=weak, gear_catalog=low)
    js = s.size_joint(arm, 0)
    assert js.adequate is False
    assert any("torque budget" in n for n in js.notes)


def test_size_arm_aggregates() -> None:
    arm = _two_joint_arm()
    result = s.size_arm(arm)
    assert len(result.joints) == 2
    assert result.recommended_psu_current_a > 0
    assert result.reach_m == pytest.approx(0.40, abs=1e-9)


# ---- TOML loading + CLI + JCFG ----------------------------------------------------------------


def test_load_sample_and_size() -> None:
    arm = s.load_arm_toml(str(SAMPLE))
    assert len(arm.joints) == 6
    result = s.size_arm(arm)
    assert result.all_adequate is True  # the sample is a feasible design
    # the heavy base/shoulder/elbow need external drivers (NEMA23 > 2 A onboard limit)
    assert "J1 base yaw" in result.joints_needing_external_driver
    assert "J2 shoulder" in result.joints_needing_external_driver


def test_jcfg_block_is_well_formed() -> None:
    arm = s.load_arm_toml(str(SAMPLE))
    result = s.size_arm(arm)
    block = s.format_jcfg_block(arm, result)
    assert block.startswith("static const JointCfg JCFG[] = {")
    assert block.count("},") == 6  # one row per joint
    assert "f," in block  # float literals present
    # a row carries the configured pins + a computed steps_per_deg
    assert "PC2," in block


def test_format_report_mentions_psu_and_jcfg() -> None:
    arm = s.load_arm_toml(str(SAMPLE))
    report = s.format_report(arm, s.size_arm(arm))
    assert "PSU:" in report
    assert "JCFG[]" in report


def test_main_returns_zero_for_feasible_sample() -> None:
    assert s.main([str(SAMPLE)]) == 0


# ---- [E] physical dimensions (CAD) -----------------------------------------------------------


def test_nema_frame_dims() -> None:
    body, bolt, _pilot, shaft = s.nema_frame_dims(17)
    assert (
        body == pytest.approx(42.3) and bolt == pytest.approx(31.0) and shaft == pytest.approx(5.0)
    )
    assert s.nema_frame_dims(23)[3] == pytest.approx(6.35)  # NEMA23 shaft
    # an unlisted size snaps to the nearest known frame
    assert s.nema_frame_dims(18) == s.nema_frame_dims(17)


def test_gt2_pulley_pitch_diameter() -> None:
    # GT2 (2 mm pitch): PD = teeth * 2 / pi -> 20T ~= 12.73 mm.
    assert s.gt2_pulley_pd_mm(20) == pytest.approx(12.732, abs=1e-3)


def test_required_tube_od_grows_with_moment() -> None:
    sigma = s.MaterialSpec().allowable_stress_pa  # Al-6061, 276/2 MPa
    od_small = s.required_tube_od_mm(5.0, 2.0, sigma)
    od_big = s.required_tube_od_mm(50.0, 2.0, sigma)
    assert od_big > od_small > 4.0  # bigger moment -> bigger OD; OD exceeds 2*wall
    # the section actually meets the stress requirement (Z >= M/sigma)
    od_m = od_big / 1000.0
    id_m = od_m - 2 * (2.0 / 1000.0)
    z = math.pi * (od_m**4 - id_m**4) / (32 * od_m)
    assert z >= 50.0 / sigma * 0.99


def test_required_rect_height_closed_form() -> None:
    sigma = s.MaterialSpec().allowable_stress_pa
    h = s.required_rect_height_mm(10.0, 20.0, sigma)
    # Z = b*h^2/6 must cover M/sigma
    z = (20.0 / 1000.0) * (h / 1000.0) ** 2 / 6.0
    assert z == pytest.approx(10.0 / sigma, rel=1e-6)


def test_material_allowable_stress() -> None:
    assert s.MaterialSpec(yield_mpa=276.0, safety=2.0).allowable_stress_pa == pytest.approx(138e6)


def test_size_joint_emits_cad_dimensions() -> None:
    arm = s.load_arm_toml(str(SAMPLE))
    js = s.size_joint(arm, 1)  # shoulder
    assert js.link_length_mm == pytest.approx(250.0)  # 0.25 m link
    assert js.bending_moment_nm > 0
    assert "tube" in js.link_section_desc  # round_tube section in the sample
    assert "NEMA23" in js.motor_mount_desc  # heavy shoulder -> NEMA23
    assert "planetary" in js.reduction_desc  # 50:1 is a gearbox, not a belt


def test_belt_reduction_reports_pulleys() -> None:
    arm = s.load_arm_toml(str(SAMPLE))
    js = s.size_joint(arm, 0)  # base uses a 10:1 belt in the sample
    assert "GT2" in js.reduction_desc and "PD" in js.reduction_desc


def test_zero_moment_returns_minimum_section() -> None:
    sigma = s.MaterialSpec().allowable_stress_pa
    assert s.required_tube_od_mm(0.0, 2.0, sigma) == pytest.approx(4.0)  # 2 * wall
    assert s.required_rect_height_mm(0.0, 20.0, sigma) == pytest.approx(20.0)  # = width


def test_rect_link_section_emits_bar() -> None:
    arm = _two_joint_arm()
    arm.link_section = "rect"
    arm.link_wall_mm = 20.0  # rect-bar width
    js = s.size_joint(arm, 1)
    assert "bar" in js.link_section_desc and arm.material.name in js.link_section_desc


def test_stiffness_sizing_grows_with_length() -> None:
    e_pa = 69e9
    # I_req = F·L³/(3·E·δ) — a longer cantilever droops more, so needs a stiffer (bigger) section.
    od_short = s.required_tube_od_for_stiffness(10.0, 0.2, e_pa, 0.2 / 200, 2.0)
    od_long = s.required_tube_od_for_stiffness(10.0, 0.5, e_pa, 0.5 / 200, 2.0)
    assert od_long > od_short > 4.0
    h_short = s.required_rect_height_for_stiffness(10.0, 0.2, e_pa, 0.2 / 200, 20.0)
    h_long = s.required_rect_height_for_stiffness(10.0, 0.5, e_pa, 0.5 / 200, 20.0)
    assert h_long > h_short
    # degenerate load -> minimum section
    assert s.required_tube_od_for_stiffness(0.0, 0.3, e_pa, 0.0015, 2.0) == pytest.approx(4.0)
    assert s.required_rect_height_for_stiffness(0.0, 0.3, e_pa, 0.0015, 20.0) == pytest.approx(20.0)


def test_deflection_governs_for_soft_long_link() -> None:
    # A long, lightly-loaded PLA link with a tight droop limit -> deflection, not stress, sets size.
    motors = [s.MotorSpec("NEMA17", 0.45, 1.5, nema_size=17)]
    gears = [s.GearOption(20, 0.8, "planetary")]
    j0 = s.JointConfig("long", "horizontal", motor_mass_kg=0.2, link_mass_kg=0.1, link_length_m=0.6)
    arm = s.ArmSpec(
        joints=[j0],
        payload_kg=0.2,
        motor_catalog=motors,
        gear_catalog=gears,
        material=s.MaterialSpec(name="PLA", yield_mpa=50.0, modulus_gpa=3.5, safety=2.0),
        link_stiffness_ratio=500.0,
    )
    js = s.size_joint(arm, 0)
    assert "deflection-governed" in js.link_section_desc


def test_stress_governs_for_short_heavy_link() -> None:
    # A SHORT link with a heavy tip load: high bending stress but tiny droop (deflection ∝ L³),
    # so STRESS sets the section. (A long link, like the sample shoulder, is deflection-governed.)
    motors = [s.MotorSpec("NEMA23", 1.9, 2.8, nema_size=23)]
    gears = [s.GearOption(50, 0.8, "planetary")]
    j0 = s.JointConfig(
        "stub", "horizontal", motor_mass_kg=0.3, link_mass_kg=0.3, link_length_m=0.05
    )
    arm = s.ArmSpec(
        joints=[j0],
        payload_kg=3.0,
        motor_catalog=motors,
        gear_catalog=gears,
        link_stiffness_ratio=100.0,
    )
    js = s.size_joint(arm, 0)
    assert "stress-governed" in js.link_section_desc


# ---- M-ARM-3 task 3.3: sizing emits the kinematic-model URDF (FR-10) ----


def test_emit_urdf_round_trips_link_lengths_and_limits(tmp_path: Path) -> None:
    """The emitted URDF carries the sizing config's link lengths + joint limits unchanged, so the
    model and the sizing calculator share one source of truth (SPEC R3 anti-drift)."""
    from pibot.arm import geometry

    arm = _two_joint_arm()  # base link 0.10 m, shoulder link 0.30 m; default limits -90..90
    urdf = s.emit_urdf(arm)
    path = tmp_path / "arm.urdf"
    path.write_text(urdf)

    model = geometry.load(path)
    assert [j.name for j in model.joints] == [jc.name for jc in arm.joints]
    for got, jc in zip(model.joints, arm.joints, strict=True):
        assert got.length_m == pytest.approx(jc.link_length_m)
        assert got.min_deg == pytest.approx(jc.min_deg)
        assert got.max_deg == pytest.approx(jc.max_deg)


def test_emit_urdf_cli_prints_a_robot(capsys: pytest.CaptureFixture[str]) -> None:
    rc = s.main([str(SAMPLE), "--emit-urdf"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "<robot" in out and 'type="revolute"' in out


def test_emit_urdf_rejects_more_joints_than_standard_axes() -> None:
    """The geometry axis convention only defines STANDARD_6R_AXES; an arm with more DOFs must fail
    loudly (the kinematic source of truth shouldn't silently guess axes for unknown joints)."""
    from pibot.arm import geometry

    motors = [s.MotorSpec("NEMA17", 0.45, 1.5)]
    gears = [s.GearOption(10, 0.9, "belt")]
    n = len(geometry.STANDARD_6R_AXES) + 1
    joints = [
        s.JointConfig(f"j{i}", "horizontal", motor_mass_kg=0.3, link_mass_kg=0.1, link_length_m=0.1)
        for i in range(n)
    ]
    arm = s.ArmSpec(joints=joints, payload_kg=0.5, motor_catalog=motors, gear_catalog=gears)
    with pytest.raises(ValueError, match="STANDARD_6R_AXES"):
        s.emit_urdf(arm)
