"""JointSolver seam (A.5) — DirectSolver, NamedPoseSolver, and composing a solver with the manager.

Proves the modular boundary (docs/plans/2026-06-13-pibot-arm-control.md): a solver turns intent into
joint-angle targets that ArmManager.move_synchronized executes, with no manager/firmware change.
"""

from __future__ import annotations

import math
import subprocess
import sys
from typing import Any

import pytest

from pibot.arm import ArmManager, DirectSolver, NamedPoseSolver, linear_joint_map
from pibot.protocol.codec import decode
from pibot.transport.base import Transport


class _Recorder(Transport):
    """Minimal transport that records the frames sent to it."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def send(self, frame: bytes) -> None:
        self.sent.append(frame)

    def recv(self, timeout: float) -> bytes | None:
        return None

    @property
    def is_open(self) -> bool:
        return True

    @property
    def info(self) -> dict[str, Any]:
        return {"backend": "recorder"}


def test_direct_solver_passes_through_and_validates() -> None:
    solver = DirectSolver(num_joints=3)
    assert solver.solve({0: 10.0, 2: -20.0}) == {0: 10.0, 2: -20.0}
    with pytest.raises(ValueError):
        solver.solve({3: 0.0})  # out of range


def test_named_pose_solver_resolves_and_lists() -> None:
    solver = NamedPoseSolver({"home": {0: 0.0, 1: 0.0}, "ready": {0: 30.0, 1: -45.0}})
    assert solver.names == ["home", "ready"]
    assert solver.solve("ready") == {0: 30.0, 1: -45.0}
    with pytest.raises(KeyError):
        solver.solve("nope")


def test_solver_output_drives_move_synchronized() -> None:
    t0, t1 = _Recorder(), _Recorder()
    arm = ArmManager([t0, t1], linear_joint_map([3, 3]))
    solver = NamedPoseSolver({"ready": {0: 60.0, 3: 90.0}})
    arm.move_synchronized(solver.solve("ready"), current={0: 0.0, 3: 0.0}, seconds=2.0)
    # J0 (board 0) travels 60° and J3 (board 1) travels 90° over 2 s → 30 and 45 deg/sec.
    assert decode(t0.sent[0], "ascii").args["dps"] == pytest.approx(30.0)
    assert decode(t1.sent[0], "ascii").args["dps"] == pytest.approx(45.0)


# ---- M-ARM-3 task 3.2: forward kinematics (needs the optional `arm-ik` extra) ----


def test_kinematics_module_imports_without_numpy() -> None:
    """`import pibot.arm.kinematics` must not pull numpy at module load (NFR-2) — checked in a fresh
    interpreter so the assertion is independent of what the rest of the test session imported."""
    code = "import sys, pibot.arm.kinematics; print('numpy' in sys.modules)"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False", "pibot.arm.kinematics imported numpy at module load"


def test_fk_at_zero_is_the_fully_extended_reach() -> None:
    pytest.importorskip("ikpy")
    from pibot.arm.kinematics import ForwardKinematics

    fk = ForwardKinematics()
    assert fk.num_joints == 6
    pose = fk.solve({})  # all joints 0° → EE straight up at the sum of link lengths
    assert pose.x == pytest.approx(0.0, abs=1e-6)
    assert pose.y == pytest.approx(0.0, abs=1e-6)
    assert pose.z == pytest.approx(0.64, abs=1e-6)  # 0.10+0.18+0.16+0.06+0.06+0.08


def test_fk_shoulder_pitch_swings_the_reach_forward() -> None:
    pytest.importorskip("ikpy")
    from pibot.arm.kinematics import ForwardKinematics

    fk = ForwardKinematics()
    # Pitch the shoulder (J1, axis Y) 90°: the 0.54 m beyond it swings from +Z to +X.
    pose = fk.solve({1: 90.0})
    assert pose.x == pytest.approx(0.54, abs=1e-3)
    assert pose.z == pytest.approx(0.10, abs=1e-3)
    assert pose.as_dict().keys() == {"x", "y", "z", "rx", "ry", "rz"}


def test_fk_base_yaw_does_not_move_the_on_axis_tip() -> None:
    pytest.importorskip("ikpy")
    from pibot.arm.kinematics import ForwardKinematics

    fk = ForwardKinematics()
    # Base yaw (J0, axis Z) rotates the arm about Z; the tip is on that axis, so it can't move.
    pose = fk.solve({0: 90.0})
    assert pose.x == pytest.approx(0.0, abs=1e-6)
    assert pose.y == pytest.approx(0.0, abs=1e-6)
    assert pose.z == pytest.approx(0.64, abs=1e-6)


def test_fk_base_yaw_orients_the_tool_frame() -> None:
    """Base yaw 90° leaves the on-axis tip put but yaws the tool frame — exercises the orientation
    (roll/pitch/yaw) output, general branch of _rpy_from_matrix."""
    pytest.importorskip("ikpy")
    from pibot.arm.kinematics import ForwardKinematics

    pose = ForwardKinematics().solve({0: 90.0})
    assert pose.rz == pytest.approx(math.pi / 2, abs=1e-6)  # yaw = 90°
    assert pose.rx == pytest.approx(0.0, abs=1e-6)
    assert pose.ry == pytest.approx(0.0, abs=1e-6)


def test_rpy_from_matrix_handles_the_gimbal_lock_singularity() -> None:
    """A ±90° pitch makes sy≈0 — `_rpy_from_matrix` must take its singularity branch (no ikpy)."""
    from pibot.arm.kinematics import _rpy_from_matrix

    # R_y(+90°): r00 = r10 = 0 → sy = 0 → the singularity path.
    m = [
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    rx, ry, rz = _rpy_from_matrix(m)
    assert rx == pytest.approx(0.0, abs=1e-9)
    assert ry == pytest.approx(math.pi / 2, abs=1e-9)
    assert rz == 0.0
