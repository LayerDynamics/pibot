"""Timed arm trajectories (M-ARM-5).

The generator emits absolute joint targets sampled along a symmetric trapezoidal progress curve.
Each frame carries the target snapshot plus the time budget to reach it from the previous frame.
`ArmManager.run_trajectory()` turns those frames into paced `jmove` commands.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from pibot.arm.kinematics import Pose


@dataclass(frozen=True)
class TrajectoryFrame:
    """One timed trajectory sample.

    ``targets`` is the absolute target per logical joint after ``dt`` seconds from the previous
    sample. The first frame is conventionally the starting snapshot with ``dt=0``.
    """

    targets: dict[int, float]
    dt: float


class CartesianSolver(Protocol):
    """The minimal seam needed for Cartesian interpolation: a pose -> joint-target solver."""

    def solve(self, target: Pose) -> dict[int, float]: ...


def _normalize_targets(targets: dict[int, float] | object) -> dict[int, float]:
    if not isinstance(targets, dict):
        raise TypeError("targets must be a dict[int, float]")
    return {int(joint): float(deg) for joint, deg in targets.items()}


def _sample_times(seconds: float, rate_hz: float) -> list[float]:
    if seconds <= 0:
        raise ValueError("seconds must be positive")
    if rate_hz <= 0:
        raise ValueError("rate_hz must be positive")
    dt = 1.0 / rate_hz
    times = [0.0]
    elapsed = 0.0
    while elapsed + dt < seconds - 1e-9:
        elapsed += dt
        times.append(elapsed)
    times.append(seconds)
    return times


def _trapezoid_progress(t: float, seconds: float, accel_fraction: float) -> float:
    if not 0.0 < accel_fraction < 0.5:
        raise ValueError("accel_fraction must be in (0, 0.5)")
    ta = seconds * accel_fraction
    tc = seconds - 2.0 * ta
    accel = 1.0 / (ta * (seconds - ta))
    if t <= 0.0:
        return 0.0
    if t >= seconds:
        return 1.0
    if t <= ta:
        return 0.5 * accel * t * t
    if t < ta + tc:
        return 0.5 * accel * ta * ta + accel * ta * (t - ta)
    remaining = seconds - t
    return 1.0 - 0.5 * accel * remaining * remaining


def joint_trajectory(
    start: dict[int, float] | object,
    goal: dict[int, float] | object,
    *,
    seconds: float,
    rate_hz: float = 20.0,
    accel_fraction: float = 0.25,
) -> list[TrajectoryFrame]:
    """Sample a synchronized joint-space ramp from ``start`` to ``goal``.

    All joints share the same normalized trapezoidal progress, so the path is monotonic per joint
    and all joints reach their exact endpoint together.
    """

    start_targets = _normalize_targets(start)
    goal_targets = _normalize_targets(goal)
    if set(start_targets) != set(goal_targets):
        raise ValueError("start and goal must cover the same joints")

    frames = [TrajectoryFrame(targets=dict(start_targets), dt=0.0)]
    prev_t = 0.0
    for t in _sample_times(seconds, rate_hz)[1:]:
        progress = _trapezoid_progress(t, seconds, accel_fraction)
        targets = {
            joint: start_targets[joint] + (goal_targets[joint] - start_targets[joint]) * progress
            for joint in sorted(goal_targets)
        }
        frames.append(TrajectoryFrame(targets=targets, dt=t - prev_t))
        prev_t = t
    return frames


def _quat_from_rpy(rx: float, ry: float, rz: float) -> tuple[float, float, float, float]:
    cr, sr = math.cos(rx / 2.0), math.sin(rx / 2.0)
    cp, sp = math.cos(ry / 2.0), math.sin(ry / 2.0)
    cy, sy = math.cos(rz / 2.0), math.sin(rz / 2.0)
    return (
        cr * cp * cy + sr * sp * sy,
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
    )


def _rpy_from_quat(q: tuple[float, float, float, float]) -> tuple[float, float, float]:
    w, x, y, z = q
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    rx = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1.0:
        ry = math.copysign(math.pi / 2.0, sinp)
    else:
        ry = math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    rz = math.atan2(siny_cosp, cosy_cosp)
    return rx, ry, rz


def _normalize_quat(q: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    norm = math.sqrt(sum(part * part for part in q))
    return tuple(part / norm for part in q)  # type: ignore[return-value]


def _slerp(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    t: float,
) -> tuple[float, float, float, float]:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    end = b
    if dot < 0.0:
        dot = -dot
        end = (-b[0], -b[1], -b[2], -b[3])
    if dot > 0.9995:
        blended = (
            a[0] + t * (end[0] - a[0]),
            a[1] + t * (end[1] - a[1]),
            a[2] + t * (end[2] - a[2]),
            a[3] + t * (end[3] - a[3]),
        )
        return _normalize_quat(blended)
    theta0 = math.acos(max(-1.0, min(1.0, dot)))
    sin_theta0 = math.sin(theta0)
    theta = theta0 * t
    sin_theta = math.sin(theta)
    s0 = math.cos(theta) - dot * sin_theta / sin_theta0
    s1 = sin_theta / sin_theta0
    return (
        s0 * a[0] + s1 * end[0],
        s0 * a[1] + s1 * end[1],
        s0 * a[2] + s1 * end[2],
        s0 * a[3] + s1 * end[3],
    )


def cartesian_trajectory(
    start_joints: dict[int, float] | object,
    start: Pose,
    goal: Pose,
    *,
    solver: CartesianSolver,
    seconds: float,
    rate_hz: float = 20.0,
    accel_fraction: float = 0.25,
) -> list[TrajectoryFrame]:
    """Interpolate a Cartesian line + SLERP orientation and solve each waypoint to joints."""

    frames = [TrajectoryFrame(targets=_normalize_targets(start_joints), dt=0.0)]
    q0 = _quat_from_rpy(start.rx, start.ry, start.rz)
    q1 = _quat_from_rpy(goal.rx, goal.ry, goal.rz)
    prev_t = 0.0
    for t in _sample_times(seconds, rate_hz)[1:]:
        progress = _trapezoid_progress(t, seconds, accel_fraction)
        q = _slerp(q0, q1, progress)
        rx, ry, rz = _rpy_from_quat(q)
        pose = Pose(
            x=start.x + (goal.x - start.x) * progress,
            y=start.y + (goal.y - start.y) * progress,
            z=start.z + (goal.z - start.z) * progress,
            rx=rx,
            ry=ry,
            rz=rz,
        )
        frames.append(
            TrajectoryFrame(targets=_normalize_targets(solver.solve(pose)), dt=t - prev_t)
        )
        prev_t = t
    return frames
