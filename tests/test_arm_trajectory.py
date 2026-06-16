"""M-ARM-5 task 5.1 — trajectory generation.

Joint-space ramps stay pure-stdlib and deterministic; Cartesian interpolation only needs a
``JointSolver`` at call time, so the module itself remains light to import.
"""

from __future__ import annotations

import math

import pytest

from pibot.arm.kinematics import Pose
from pibot.arm.trajectory import TrajectoryFrame, cartesian_trajectory, joint_trajectory


def test_joint_trajectory_is_monotonic_velocity_bounded_and_hits_endpoints() -> None:
    frames = joint_trajectory({0: 0.0, 1: 10.0}, {0: 90.0, 1: -20.0}, seconds=3.0, rate_hz=4.0)

    assert frames[0] == TrajectoryFrame(targets={0: 0.0, 1: 10.0}, dt=0.0)
    assert frames[-1].targets == pytest.approx({0: 90.0, 1: -20.0})

    j0 = [frame.targets[0] for frame in frames]
    j1 = [frame.targets[1] for frame in frames]
    assert j0 == sorted(j0)
    assert j1 == sorted(j1, reverse=True)

    peak_dps_joint0 = 90.0 / 2.25  # duration / (1 - accel_fraction) with the default 25% ramps
    peak_dps_joint1 = 30.0 / 2.25
    for prev, cur in zip(frames, frames[1:], strict=False):
        assert cur.dt > 0.0
        assert abs(cur.targets[0] - prev.targets[0]) / cur.dt <= peak_dps_joint0 + 1e-6
        assert abs(cur.targets[1] - prev.targets[1]) / cur.dt <= peak_dps_joint1 + 1e-6


def test_joint_trajectory_uses_fixed_dt_and_exact_final_remainder() -> None:
    frames = joint_trajectory({0: 0.0}, {0: 10.0}, seconds=1.0, rate_hz=3.0)

    # frame[0] is the start snapshot; every later frame advances by either the sampling period or
    # the exact remainder that lands the final point on the requested duration.
    assert [round(frame.dt, 6) for frame in frames[1:]] == [0.333333, 0.333333, 0.333333]
    assert frames[-1].targets == {0: 10.0}


def test_cartesian_trajectory_interpolates_position_and_orientation_through_solver() -> None:
    seen: list[Pose] = []

    class RecordingSolver:
        def solve(self, target: Pose) -> dict[int, float]:
            seen.append(target)
            return {0: target.x * 1000.0}

    frames = cartesian_trajectory(
        {0: 0.0},
        Pose(0.0, 0.0, 0.3, 0.0, 0.0, 0.0),
        Pose(0.1, 0.2, 0.5, 0.0, 0.0, math.pi / 2),
        solver=RecordingSolver(),
        seconds=1.0,
        rate_hz=2.0,
    )

    assert frames[0] == TrajectoryFrame(targets={0: 0.0}, dt=0.0)
    assert frames[-1].targets == {0: 100.0}
    assert len(seen) == 2

    mid, end = seen
    assert mid.x == pytest.approx(0.05)
    assert mid.y == pytest.approx(0.1)
    assert mid.z == pytest.approx(0.4)
    assert mid.rz == pytest.approx(math.pi / 4, abs=1e-6)
    assert end.as_dict() == pytest.approx(Pose(0.1, 0.2, 0.5, 0.0, 0.0, math.pi / 2).as_dict())
