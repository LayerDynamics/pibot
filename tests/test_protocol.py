"""T3.1 — Pi↔Arduino wire protocol codec: ASCII+CRC, JSON-lines, seq tracking.

This is the layer that, if wrong, sends a garbled motion command to the robot. It is
tested exhaustively, including a fuzz pass that the decoder must never crash on.
"""

from __future__ import annotations

import json

import pytest

from pibot.protocol import codec
from pibot.protocol.codec import DecodeError, Message, MessageType, SeqTracker, crc8

# ---- CRC8 ----------------------------------------------------------------


def test_crc8_known_vector() -> None:
    # CRC-8 (poly 0x07, init 0x00) of the canonical check string is 0xF4.
    assert crc8(b"123456789") == 0xF4
    assert crc8(b"") == 0x00


# ---- ASCII command round-trips -------------------------------------------


def _rt(msg: Message, encoding: str) -> Message:
    return codec.decode(codec.encode(msg, encoding), encoding)


@pytest.mark.parametrize("encoding", ["ascii", "json"])
@pytest.mark.parametrize(
    "msg",
    [
        Message(MessageType.COMMAND, 5, "drive", {"v": 0.5, "w": 0.0}),
        Message(MessageType.COMMAND, 0, "servo", {"id": 1, "deg": 90}),
        Message(MessageType.COMMAND, 200, "motor", {"id": 2, "pwm": -128}),
        Message(MessageType.COMMAND, 7, "stop", {}),
        Message(MessageType.COMMAND, 8, "estop", {}),
        Message(MessageType.COMMAND, 9, "ping", {}),
        Message(MessageType.COMMAND, 10, "set", {"param": "max_speed", "value": 1.5}),
        Message(MessageType.TELEMETRY, 11, "battery", {"volts": 12.4}),
        Message(MessageType.TELEMETRY, 12, "encoder", {"left": 1024, "right": -50}),
        Message(MessageType.ACK, 13),
        Message(MessageType.NAK, 14, reason="crc"),
    ],
)
def test_round_trip_both_encodings(msg: Message, encoding: str) -> None:
    assert _rt(msg, encoding) == msg


def test_ascii_frame_shape() -> None:
    frame = codec.encode(Message(MessageType.COMMAND, 5, "drive", {"v": 0.5, "w": 0.0}), "ascii")
    assert frame.startswith(b">5,drive,")
    assert frame.endswith(b"\n")
    assert b"*" in frame  # CRC delimiter
    # telemetry uses '<'
    t = codec.encode(Message(MessageType.TELEMETRY, 5, "battery", {"volts": 12.4}), "ascii")
    assert t.startswith(b"<5,battery,")


def test_ascii_ack_nak_shape() -> None:
    assert codec.encode(Message(MessageType.ACK, 13), "ascii") == b"ACK 13\n"
    assert codec.encode(Message(MessageType.NAK, 14, reason="crc"), "ascii") == b"NAK 14 crc\n"


# ---- corruption / CRC enforcement ----------------------------------------


def test_corrupted_crc_rejected() -> None:
    frame = bytearray(codec.encode(Message(MessageType.COMMAND, 5, "drive", {"v": 0.5, "w": 0.0})))
    # flip a payload byte so the CRC no longer matches
    frame[3] ^= 0x20
    with pytest.raises(DecodeError) as exc:
        codec.decode(bytes(frame), "ascii")
    assert exc.value.reason == "crc"


def test_garbage_frame_rejected() -> None:
    with pytest.raises(DecodeError):
        codec.decode(b">not-a-valid-frame\n", "ascii")


# ---- cross-encoding equivalence ------------------------------------------


def test_both_encodings_decode_to_same_message() -> None:
    msg = Message(MessageType.COMMAND, 5, "drive", {"v": 0.5, "w": 0.0})
    assert codec.decode(codec.encode(msg, "ascii"), "ascii") == codec.decode(
        codec.encode(msg, "json"), "json"
    )


def test_json_shape_is_compact() -> None:
    frame = codec.encode(Message(MessageType.COMMAND, 5, "drive", {"v": 0.5, "w": 0.0}), "json")
    obj = json.loads(frame)
    assert obj == {"seq": 5, "cmd": "drive", "v": 0.5, "w": 0.0}


# ---- sequence tracking ---------------------------------------------------


def test_seq_tracker_wraps_8bit() -> None:
    t = SeqTracker()
    seqs = [t.next() for _ in range(258)]
    assert seqs[:3] == [0, 1, 2]
    assert seqs[255] == 255
    assert seqs[256] == 0  # wrap
    assert seqs[257] == 1


def test_seq_observe_detects_dup_and_out_of_order() -> None:
    t = SeqTracker()
    assert t.observe(0) == "ok"
    assert t.observe(1) == "ok"
    assert t.observe(1) == "duplicate"
    assert t.observe(5) == "out_of_order"
    assert t.observe(6) == "ok"
    # wrap boundary is in-order
    t2 = SeqTracker()
    t2.observe(255)
    assert t2.observe(0) == "ok"


# ---- fuzz: the decoder must never crash ----------------------------------


def test_decode_never_crashes_on_garbage() -> None:
    import random

    rng = random.Random(1234)
    for _ in range(2000):
        n = rng.randint(0, 40)
        raw = bytes(rng.randint(0, 255) for _ in range(n))
        for encoding in ("ascii", "json"):
            try:
                result = codec.decode(raw, encoding)
                assert isinstance(result, Message)
            except DecodeError:
                pass  # expected for malformed input


# ---- exhaustive decode-error branches ------------------------------------


def _crc_frame(payload: str, marker: str = ">") -> bytes:
    return f"{marker}{payload}*{crc8(payload.encode()):02X}\n".encode()


@pytest.mark.parametrize(
    "frame,reason",
    [
        (b"\n", "empty"),
        (b"?5,drive,0,0*00\n", "marker"),
        (b">5,drive,0.5,0.0\n", "frame"),  # no CRC delimiter
        (b">5,ping*ZZ\n", "crc"),  # non-hex CRC
        (b"ACK notanum\n", "seq"),
    ],
)
def test_ascii_decode_error_reasons(frame: bytes, reason: str) -> None:
    with pytest.raises(DecodeError) as exc:
        codec.decode(frame, "ascii")
    assert exc.value.reason == reason


@pytest.mark.parametrize(
    "payload,reason",
    [
        ("5", "fields"),  # seq only, no name
        ("notanum,ping", "seq"),  # non-integer seq
        ("300,ping", "seq"),  # seq out of 0..255
        ("5,drive,0.5", "arity"),  # drive needs v and w
    ],
)
def test_ascii_decode_error_reasons_with_valid_crc(payload: str, reason: str) -> None:
    with pytest.raises(DecodeError) as exc:
        codec.decode(_crc_frame(payload), "ascii")
    assert exc.value.reason == reason


def test_ascii_unknown_command_keeps_positional_args() -> None:
    # Unknown command names decode with generic positional arg keys (no error).
    msg = codec.decode(_crc_frame("5,wiggle,1,2"), "ascii")
    assert msg.name == "wiggle"
    assert msg.args == {"arg0": 1, "arg1": 2}


@pytest.mark.parametrize(
    "frame,reason",
    [
        (b"not json\n", "json"),
        (b"[]\n", "schema"),  # not an object
        (b'{"cmd":"ping"}\n', "schema"),  # missing seq
        (b'{"seq":true,"ack":true}\n', "seq"),  # bool seq
        (b'{"seq":1}\n', "schema"),  # no cmd/tlm/ack/nak
    ],
)
def test_json_decode_error_reasons(frame: bytes, reason: str) -> None:
    with pytest.raises(DecodeError) as exc:
        codec.decode(frame, "json")
    assert exc.value.reason == reason


def test_unknown_encoding_raises_value_error() -> None:
    with pytest.raises(ValueError):
        codec.encode(Message(MessageType.ACK, 1), "morse")
    with pytest.raises(ValueError):
        codec.decode(b"ACK 1\n", "morse")


def test_non_utf8_bytes_rejected() -> None:
    with pytest.raises(DecodeError) as exc:
        codec.decode(b"\xff\xfe\n", "ascii")
    assert exc.value.reason == "encoding"
