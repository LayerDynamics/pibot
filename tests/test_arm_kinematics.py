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


# ---- M-ARM-4 task 4.1: the `arm-ik` extra is present in the gate's test env ----


def test_arm_ik_extra_is_installed_in_the_test_env() -> None:
    """The gate installs `pibot[arm-ik]` (ikpy) so the FK/IK tests RUN here rather than
    importorskip-skipping — keeping the suite hermetic with zero skips (CLAUDE.md). A clean
    failure here points straight at the fix: `pip install -e '.[arm-ik]'`."""
    try:
        import ikpy.chain  # noqa: F401  — the symbol IKSolver/ForwardKinematics actually use
    except ImportError as exc:  # pragma: no cover - only reached when the extra is missing
        pytest.fail(f"ikpy missing — run: pip install -e '.[arm-ik]' ({exc})")


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


# ---- M-ARM-4 task 4.2: inverse kinematics behind the JointSolver seam ----


def test_iksolver_round_trips_a_reachable_pose() -> None:
    """FK∘IK ≈ identity: IK-solving the pose FK produced reproduces that pose (within tolerance).
    The joint angles may differ (IK can pick another branch); the achieved EE pose must match."""
    pytest.importorskip("ikpy")
    from pibot.arm.kinematics import ForwardKinematics, IKSolver

    fk = ForwardKinematics()
    ik = IKSolver()
    assert ik.num_joints == 6
    target_joints = {1: 30.0, 2: -25.0, 4: 20.0}
    pose = fk.solve(target_joints)

    solved = ik.solve(pose)
    assert set(solved) == set(range(6))  # one angle per logical joint

    achieved = fk.solve(solved)
    assert achieved.x == pytest.approx(pose.x, abs=2e-3)
    assert achieved.y == pytest.approx(pose.y, abs=2e-3)
    assert achieved.z == pytest.approx(pose.z, abs=2e-3)
    assert achieved.rx == pytest.approx(pose.rx, abs=2e-2)
    assert achieved.ry == pytest.approx(pose.ry, abs=2e-2)
    assert achieved.rz == pytest.approx(pose.rz, abs=2e-2)


def test_iksolver_keeps_every_joint_within_its_limit() -> None:
    """A solved configuration never violates a joint limit (SPEC R5) — the solver must not emit
    motor targets outside the URDF travel range."""
    pytest.importorskip("ikpy")
    from pibot.arm import geometry
    from pibot.arm.kinematics import ForwardKinematics, IKSolver

    model = geometry.load()
    fk = ForwardKinematics()
    ik = IKSolver()
    solved = ik.solve(fk.solve({0: 40.0, 1: 35.0, 2: -30.0, 5: 50.0}))
    for jid, deg in solved.items():
        lo, hi = model.joints[jid].min_deg, model.joints[jid].max_deg
        assert lo - 1e-3 <= deg <= hi + 1e-3, f"J{jid}={deg} outside [{lo}, {hi}]"


def test_iksolver_rejects_an_unreachable_pose() -> None:
    """A pose far outside the workspace must raise (never emit an unclamped best-effort result)."""
    pytest.importorskip("ikpy")
    from pibot.arm.kinematics import IKSolver, Pose

    ik = IKSolver()
    with pytest.raises(ValueError):
        ik.solve(Pose(x=10.0, y=0.0, z=0.0, rx=0.0, ry=0.0, rz=0.0))


def test_iksolver_is_a_jointsolver() -> None:
    """IKSolver satisfies the JointSolver seam, so its output drives ArmManager unchanged."""
    pytest.importorskip("ikpy")
    from pibot.arm.kinematics import ForwardKinematics, IKSolver, JointSolver

    solver: JointSolver[object] = IKSolver()
    targets = solver.solve(ForwardKinematics().solve({1: 20.0}))
    assert all(isinstance(v, float) for v in targets.values())


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
