"""M-ARM-5 task 5.3 — pose/program model + validation."""

from __future__ import annotations

import pytest

from pibot.arm.programs import Pose, Program, ProgramStep, record_pose


def test_pose_json_roundtrip() -> None:
    pose = Pose(
        name="ready",
        joints={0: 10.0, 1: -5.0},
        gripper=30.0,
        tool=True,
        cartesian={"x": 0.3, "y": 0.0, "z": 0.4, "rx": 0.0, "ry": 0.1, "rz": 0.0},
        created=123.0,
    )

    restored = Pose.from_dict(pose.as_dict())
    assert restored == pose


def test_record_pose_from_telemetry_snapshot() -> None:
    snap = {
        "positions": {"0": 12.5, "1": -4.0},
        "gripper": {"deg": 25.0, "tool": True},
        "pose": {"x": 0.5, "y": 0.0, "z": 0.3, "rx": 0.0, "ry": 0.0, "rz": 0.0},
    }

    pose = record_pose("picked", snap, created=99.0)
    assert pose.name == "picked"
    assert pose.joints == {0: 12.5, 1: -4.0}
    assert pose.gripper == 25.0
    assert pose.tool is True
    assert pose.cartesian == {"x": 0.5, "y": 0.0, "z": 0.3, "rx": 0.0, "ry": 0.0, "rz": 0.0}
    assert pose.created == 99.0


def test_program_rejects_malformed_step() -> None:
    with pytest.raises(ValueError, match="moveJ"):
        Program.from_dict(
            {"name": "bad", "created": 1.0, "steps": [{"kind": "moveJ", "seconds": 1.0}]}
        )


def test_program_expands_wait_and_loop_steps() -> None:
    program = Program(
        name="pick",
        created=1.0,
        steps=(
            ProgramStep(kind="moveJ", pose="home", seconds=1.0),
            ProgramStep(
                kind="loop",
                count=2,
                steps=(
                    ProgramStep(kind="wait", seconds=0.25),
                    ProgramStep(kind="grip", deg=20.0),
                ),
            ),
        ),
    )

    expanded = list(program.expanded_steps())
    assert [step.kind for step in expanded] == ["moveJ", "wait", "grip", "wait", "grip"]
    assert expanded[1].seconds == pytest.approx(0.25)
    assert expanded[2].deg == pytest.approx(20.0)
