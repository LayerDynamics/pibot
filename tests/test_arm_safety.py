"""M-ARM-1 task 1.1 — host arm safety gate (``pibot/arm/safety.py``).

Pure validators, no I/O: joint-id range, per-joint angle clamp to ``[min_deg, max_deg]``,
velocity clamp to ``±max_dps``, homing-required-before-``jpos``/``jmove``/``move``, and
e-stop-latched refusal of every motion command. The mutable latch/homed state is passed in
explicitly so the validators stay pure (the agent owns the live state); this mirrors
``pibot.control.safety`` for the robot link.
"""

from __future__ import annotations

from pibot.arm.safety import ArmGate, JointLimit


def _gate() -> ArmGate:
    # J0 wide + fast, J1 narrow + slow, J2 default-ish — so per-joint lookup is observable.
    return ArmGate(
        [
            JointLimit(min_deg=-180.0, max_deg=180.0, max_dps=120.0),
            JointLimit(min_deg=-45.0, max_deg=90.0, max_dps=30.0),
            JointLimit(min_deg=-90.0, max_deg=90.0, max_dps=60.0),
        ]
    )


# ---- construction ---------------------------------------------------------


def test_with_defaults_builds_one_permissive_limit_per_joint() -> None:
    gate = ArmGate.with_defaults(4)
    assert gate.num_joints == 4
    lim = gate.limit(0)
    assert lim.min_deg == -180.0
    assert lim.max_deg == 180.0
    assert lim.max_dps == 90.0


def test_per_joint_limit_lookup() -> None:
    gate = _gate()
    assert gate.num_joints == 3
    assert gate.limit(1).max_deg == 90.0
    assert gate.limit(1).max_dps == 30.0


# ---- jpos -----------------------------------------------------------------


def test_jpos_accepts_in_range_when_homed() -> None:
    r = _gate().jpos(0, 45.0, estopped=False, homed={0})
    assert r.ok
    assert r.args["deg"] == 45.0


def test_jpos_clamps_over_range_angle_to_joint_limit() -> None:
    r = _gate().jpos(1, 999.0, estopped=False, homed={1})
    assert r.ok
    assert r.args["deg"] == 90.0  # J1 max
    r = _gate().jpos(1, -999.0, estopped=False, homed={1})
    assert r.ok
    assert r.args["deg"] == -45.0  # J1 min


def test_jpos_rejected_when_unhomed() -> None:
    r = _gate().jpos(0, 10.0, estopped=False, homed=set())
    assert not r.ok
    assert "homed" in r.reason


def test_jpos_rejected_when_estop_latched() -> None:
    r = _gate().jpos(0, 10.0, estopped=True, homed={0})
    assert not r.ok
    assert "estop" in r.reason


def test_jpos_rejected_for_out_of_range_joint() -> None:
    r = _gate().jpos(9, 10.0, estopped=False, homed={9})
    assert not r.ok
    assert "range" in r.reason


# ---- jmove (absolute move at a speed) -------------------------------------


def test_jmove_clamps_angle_and_speed_and_requires_homing() -> None:
    r = _gate().jmove(1, 200.0, 999.0, estopped=False, homed={1})
    assert r.ok
    assert r.args["deg"] == 90.0  # clamped to J1 max angle
    assert r.args["dps"] == 30.0  # clamped to J1 max speed

    unhomed = _gate().jmove(1, 10.0, 5.0, estopped=False, homed=set())
    assert not unhomed.ok
    assert "homed" in unhomed.reason


# ---- jvel (jog) — no homing required, but clamped + estop-gated -----------


def test_jvel_clamps_velocity_magnitude_to_joint_max() -> None:
    r = _gate().jvel(2, 999.0, estopped=False)
    assert r.ok
    assert r.args["dps"] == 60.0
    r = _gate().jvel(2, -999.0, estopped=False)
    assert r.ok
    assert r.args["dps"] == -60.0


def test_jvel_does_not_require_homing() -> None:
    # Jogging an un-homed joint is allowed (firmware applies soft limits only once homed).
    r = _gate().jvel(0, 10.0, estopped=False)
    assert r.ok


def test_jvel_rejected_when_estop_latched() -> None:
    r = _gate().jvel(0, 10.0, estopped=True)
    assert not r.ok
    assert "estop" in r.reason


# ---- jstop — always permitted (it reduces motion), even while latched -----


def test_jstop_allowed_even_when_estopped() -> None:
    r = _gate().jstop(0)
    assert r.ok
    r = _gate().jstop(9)
    assert not r.ok  # but the joint id must still be valid


# ---- home — gated by estop, does not require prior homing ------------------


def test_home_allowed_when_unhomed_but_refused_under_estop() -> None:
    assert _gate().home(0, estopped=False).ok
    refused = _gate().home(0, estopped=True)
    assert not refused.ok
    assert "estop" in refused.reason


# ---- move (synchronized multi-joint arrival) ------------------------------


def test_move_clamps_each_target_and_requires_homing_and_telemetry() -> None:
    gate = _gate()
    r = gate.move(
        {0: 999.0, 1: 10.0},
        current={0: 0.0, 1: 0.0},
        seconds=2.0,
        estopped=False,
        homed={0, 1},
    )
    assert r.ok
    assert r.targets == {0: 180.0, 1: 10.0}  # J0 angle clamped to its max


def test_move_rejected_when_a_joint_is_unhomed() -> None:
    r = _gate().move({0: 10.0}, current={0: 0.0}, seconds=1.0, estopped=False, homed=set())
    assert not r.ok
    assert "homed" in r.reason


def test_move_rejected_without_telemetry_for_a_joint() -> None:
    r = _gate().move({0: 10.0}, current={}, seconds=1.0, estopped=False, homed={0})
    assert not r.ok
    assert "telemetry" in r.reason


def test_move_rejected_under_estop() -> None:
    r = _gate().move({0: 10.0}, current={0: 0.0}, seconds=1.0, estopped=True, homed={0})
    assert not r.ok
    assert "estop" in r.reason


def test_move_rejected_for_nonpositive_seconds() -> None:
    r = _gate().move({0: 10.0}, current={0: 0.0}, seconds=0.0, estopped=False, homed={0})
    assert not r.ok
