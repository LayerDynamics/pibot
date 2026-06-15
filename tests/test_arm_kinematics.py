"""JointSolver seam (A.5) — DirectSolver, NamedPoseSolver, and composing a solver with the manager.

Proves the modular boundary (docs/plans/2026-06-13-pibot-arm-control.md): a solver turns intent into
joint-angle targets that ArmManager.move_synchronized executes, with no manager/firmware change.
"""

from __future__ import annotations

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
