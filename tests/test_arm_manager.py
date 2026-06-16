"""ArmManager — logical-joint routing across boards + telemetry aggregation (no hardware).

Verifies M-arm phase A.3 (docs/plans/2026-06-13-pibot-arm-control.md): each joint command goes to
the board/channel that owns it, whole-arm safety broadcasts to every board, and ``joints`` telemetry
is re-keyed by logical joint.
"""

from __future__ import annotations

from typing import Any

import pytest

from pibot.arm import ArmManager, GripperState, JointRef, linear_joint_map
from pibot.arm.trajectory import TrajectoryFrame
from pibot.protocol.codec import Message, MessageType, decode, encode
from pibot.transport.base import Transport


class FakeTransport(Transport):
    """Records sent frames; replays injected frames on recv. No real link."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self._rx: list[bytes] = []
        self._open = True

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def send(self, frame: bytes) -> None:
        self.sent.append(frame)

    def recv(self, timeout: float) -> bytes | None:
        return self._rx.pop(0) if self._rx else None

    def inject(self, frame: bytes) -> None:
        self._rx.append(frame)

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def info(self) -> dict[str, Any]:
        return {"backend": "fake"}


def _joints_telemetry(positions: list[float]) -> bytes:
    args = {f"j{i}": p for i, p in enumerate(positions)}
    return encode(Message(MessageType.TELEMETRY, 0, "joints", args), "ascii")


def _make_arm() -> tuple[ArmManager, FakeTransport, FakeTransport]:
    t0, t1 = FakeTransport(), FakeTransport()
    return ArmManager([t0, t1], linear_joint_map([3, 3])), t0, t1


def test_linear_joint_map_splits_3_3() -> None:
    m = linear_joint_map([3, 3])
    assert len(m) == 6
    assert m[0] == JointRef(0, 0)
    assert m[2] == JointRef(0, 2)
    assert m[3] == JointRef(1, 0)
    assert m[5] == JointRef(1, 2)


def test_jpos_routes_to_owning_board_and_channel() -> None:
    arm, t0, t1 = _make_arm()
    arm.jpos(4, 30.0)  # logical J4 → board 1, channel 1
    assert arm.num_joints == 6
    assert t0.sent == []
    msg = decode(t1.sent[0], "ascii")
    assert msg.name == "jpos"
    assert msg.args["id"] == 1
    assert msg.args["deg"] == 30.0


def test_jvel_jstop_home_route_with_channel() -> None:
    arm, t0, _ = _make_arm()
    arm.jvel(1, -5.0)  # board 0, ch 1
    arm.jstop(0)  # board 0, ch 0
    arm.home(2)  # board 0, ch 2
    names = [decode(f, "ascii").name for f in t0.sent]
    assert names == ["jvel", "jstop", "home"]
    jvel = decode(t0.sent[0], "ascii")
    assert jvel.args["id"] == 1 and jvel.args["dps"] == -5.0


def test_estop_and_enable_broadcast_to_all_boards() -> None:
    arm, t0, t1 = _make_arm()
    arm.estop()
    assert decode(t0.sent[-1], "ascii").name == "estop"
    assert decode(t1.sent[-1], "ascii").name == "estop"
    arm.enable(False)
    on = decode(t0.sent[-1], "ascii")
    assert on.name == "enable" and on.args["on"] == 0


def test_clear_estop_sends_set_zero() -> None:
    arm, t0, _ = _make_arm()
    arm.clear_estop()
    msg = decode(t0.sent[-1], "ascii")
    assert msg.name == "set"
    assert int(msg.args["param"]) == 0  # firmware clears the latch on args[0]==0


def test_positions_aggregate_and_skip_corrupt() -> None:
    arm, t0, t1 = _make_arm()
    t0.inject(b">0,joints,bad*00\n")  # corrupt → skipped, not crash
    t0.inject(_joints_telemetry([10.0, 20.0, 30.0]))
    t1.inject(_joints_telemetry([40.0, 50.0, 60.0]))
    assert arm.positions(timeout=0.0) == {0: 10.0, 1: 20.0, 2: 30.0, 3: 40.0, 4: 50.0, 5: 60.0}


def test_joint_referencing_missing_board_raises() -> None:
    with pytest.raises(ValueError):
        ArmManager([FakeTransport()], [JointRef(0, 0), JointRef(1, 0)])


def test_jmove_routes_with_speed() -> None:
    arm, _, t1 = _make_arm()
    arm.jmove(3, 90.0, 45.0)  # logical J3 → board 1, ch 0
    msg = decode(t1.sent[0], "ascii")
    assert msg.name == "jmove"
    assert msg.args["id"] == 0
    assert msg.args["deg"] == 90.0
    assert msg.args["dps"] == 45.0


def test_move_synchronized_scales_speed_by_distance() -> None:
    arm, t0, _ = _make_arm()
    # J0 travels 90°, J1 travels 45°, both over 3 s → 30 and 15 deg/sec so they finish together.
    arm.move_synchronized({0: 90.0, 1: 45.0}, current={0: 0.0, 1: 0.0}, seconds=3.0)
    cmds = [decode(f, "ascii") for f in t0.sent]
    assert [c.name for c in cmds] == ["jmove", "jmove"]
    dps = {int(c.args["id"]): c.args["dps"] for c in cmds}
    assert dps[0] == pytest.approx(30.0)
    assert dps[1] == pytest.approx(15.0)


def test_move_synchronized_requires_current_and_positive_time() -> None:
    arm, _, _ = _make_arm()
    with pytest.raises(ValueError):
        arm.move_synchronized({0: 10.0}, current={0: 0.0}, seconds=0.0)
    with pytest.raises(KeyError):
        arm.move_synchronized({0: 10.0}, current={}, seconds=1.0)


def test_open_close_propagate_to_every_board() -> None:
    t0, t1 = FakeTransport(), FakeTransport()
    t0.close()
    t1.close()  # start from a closed state
    arm = ArmManager([t0, t1], linear_joint_map([1, 1]))
    arm.open()
    assert t0.is_open and t1.is_open
    arm.close()
    assert not t0.is_open and not t1.is_open


def _grip_telemetry(deg: float, tool: float) -> bytes:
    return encode(Message(MessageType.TELEMETRY, 0, "grip", {"deg": deg, "tool": tool}), "ascii")


def test_grip_and_tool_route_to_the_gripper_board() -> None:
    t0, t1 = FakeTransport(), FakeTransport()
    arm = ArmManager([t0, t1], linear_joint_map([3, 3]), gripper_board=1)
    arm.grip(40.0)
    arm.tool(True)
    assert t0.sent == []  # the gripper is on board 1 only
    grip = decode(t1.sent[0], "ascii")
    assert grip.name == "grip" and grip.args["deg"] == 40.0
    tool = decode(t1.sent[1], "ascii")
    assert tool.name == "tool" and tool.args["on"] == 1


def test_gripper_board_defaults_to_zero() -> None:
    t0, t1 = FakeTransport(), FakeTransport()
    arm = ArmManager([t0, t1], linear_joint_map([3, 3]))
    arm.grip(10.0)
    assert decode(t0.sent[0], "ascii").name == "grip"


def test_gripper_board_out_of_range_raises() -> None:
    with pytest.raises(ValueError):
        ArmManager([FakeTransport()], linear_joint_map([1]), gripper_board=2)


def test_positions_captures_gripper_telemetry() -> None:
    t0, t1 = FakeTransport(), FakeTransport()
    arm = ArmManager([t0, t1], linear_joint_map([3, 3]), gripper_board=1)
    assert arm.gripper() is None
    t1.inject(_grip_telemetry(33.0, 1.0))
    arm.positions(timeout=0.0)  # the drain also captures the gripper frame
    g = arm.gripper()
    assert g == GripperState(deg=33.0, tool=True)


def test_open_partial_failure_rolls_back_already_opened() -> None:
    class FailingOpenTransport(FakeTransport):
        def open(self) -> None:
            raise RuntimeError("cannot open this board")

    t0 = FakeTransport()
    t0.close()
    bad = FailingOpenTransport()
    bad.close()
    arm = ArmManager([t0, bad], linear_joint_map([1, 1]))
    with pytest.raises(RuntimeError):
        arm.open()
    # The board that did open is closed again, so a failed open leaves no port leaked.
    assert not t0.is_open


def test_run_trajectory_sends_frames_in_order_at_the_right_cadence() -> None:
    arm, t0, _ = _make_arm()
    slept: list[float] = []

    arm.run_trajectory(
        [
            TrajectoryFrame(targets={0: 0.0, 1: 0.0}, dt=0.0),
            TrajectoryFrame(targets={0: 30.0, 1: 15.0}, dt=1.0),
            TrajectoryFrame(targets={0: 60.0, 1: 30.0}, dt=2.0),
        ],
        abort_check=lambda: False,
        sleep=slept.append,
    )

    cmds = [decode(frame, "ascii") for frame in t0.sent]
    assert [(cmd.name, int(cmd.args["id"])) for cmd in cmds] == [
        ("jmove", 0),
        ("jmove", 1),
        ("jmove", 0),
        ("jmove", 1),
    ]
    assert cmds[0].args["deg"] == 30.0
    assert cmds[0].args["dps"] == pytest.approx(30.0)
    assert cmds[3].args["deg"] == 30.0
    assert cmds[3].args["dps"] == pytest.approx(7.5)
    assert slept == [1.0, 2.0]


def test_run_trajectory_aborts_before_the_next_frame() -> None:
    arm, t0, _ = _make_arm()
    checks = iter([False, True])

    arm.run_trajectory(
        [
            TrajectoryFrame(targets={0: 0.0}, dt=0.0),
            TrajectoryFrame(targets={0: 10.0}, dt=0.5),
            TrajectoryFrame(targets={0: 20.0}, dt=0.5),
        ],
        abort_check=lambda: next(checks),
        sleep=lambda _dt: None,
    )

    cmds = [decode(frame, "ascii") for frame in t0.sent]
    assert len(cmds) == 1
    assert cmds[0].name == "jmove"
    assert cmds[0].args["deg"] == pytest.approx(10.0)
