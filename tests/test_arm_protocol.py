"""Wire-protocol round-trip for the robot-arm joint commands.

No-hardware verification for the arm controller (M-arm phase A.1,
docs/plans/2026-06-13-pibot-arm-control.md): the host codec must speak the joint protocol
(`jpos`/`jvel`/`jstop`/`home`/`enable`) on both wire encodings, and the firmware-mirror
:class:`~pibot.control.echo.EchoResponder` must ACK each — the same contract the C++ side
(``firmware/pibot_arm_stm32``) implements.
"""

from __future__ import annotations

import pytest

from pibot.control.echo import EchoResponder
from pibot.protocol.codec import DecodeError, Message, MessageType, decode, encode

ARM_CMDS: list[tuple[str, dict[str, float]]] = [
    ("jpos", {"id": 1, "deg": 45.0}),
    ("jmove", {"id": 1, "deg": 90.0, "dps": 30.0}),
    ("jvel", {"id": 0, "dps": -12.5}),
    ("jstop", {"id": 2}),
    ("home", {"id": 0}),
    ("enable", {"on": 1}),
    # M-ARM-2 gripper / end-effector verbs (mirrored in firmware/pibot_arm_stm32).
    ("grip", {"deg": 35.0}),
    ("tool", {"on": 1}),
]


@pytest.mark.parametrize("encoding", ["ascii", "json"])
@pytest.mark.parametrize("name,args", ARM_CMDS)
def test_arm_command_wire_roundtrip(encoding: str, name: str, args: dict[str, float]) -> None:
    """encode → decode reproduces the joint command exactly (ASCII CRC and JSON)."""
    out = decode(encode(Message(MessageType.COMMAND, 7, name, args), encoding), encoding)
    assert out.type is MessageType.COMMAND
    assert out.name == name
    assert out.seq == 7
    for key, value in args.items():
        assert out.args[key] == value


@pytest.mark.parametrize("encoding", ["ascii", "json"])
@pytest.mark.parametrize("name,args", ARM_CMDS)
def test_arm_command_acked_by_echo_stand(encoding: str, name: str, args: dict[str, float]) -> None:
    """The firmware-mirror echo stand ACKs every joint command (matches pibot_arm_stm32)."""
    responder = EchoResponder(encoding=encoding)
    frames = responder.feed(encode(Message(MessageType.COMMAND, 9, name, args), encoding))
    assert frames, "echo stand produced no response"
    ack = decode(frames[0], encoding)
    assert ack.type is MessageType.ACK
    assert ack.seq == 9


@pytest.mark.parametrize("encoding", ["ascii", "json"])
def test_grip_telemetry_roundtrip(encoding: str) -> None:
    """The gripper telemetry frame (angle + tool state) round-trips on both encodings."""
    msg = Message(MessageType.TELEMETRY, 3, "grip", {"deg": 42.5, "tool": 1.0})
    out = decode(encode(msg, encoding), encoding)
    assert out.type is MessageType.TELEMETRY
    assert out.name == "grip"
    assert out.args["deg"] == 42.5
    assert out.args["tool"] == 1.0


def test_bad_grip_frame_raises_decode_error() -> None:
    """A corrupt gripper frame is rejected with DecodeError, never a crash."""
    with pytest.raises(DecodeError):
        decode(b">7,grip,35*00\n", "ascii")  # wrong CRC
