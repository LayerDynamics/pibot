"""The Pi↔Arduino framing codec.

Frames (ASCII encoding):
    command   : ``>SEQ,NAME,ARG...*CC\n``   (CC = CRC-8 hex over the payload)
    telemetry : ``<SEQ,TYPE,FIELD...*CC\n``
    ack       : ``ACK SEQ\n``
    nak       : ``NAK SEQ REASON\n``

JSON encoding (one object per line):
    command   : ``{"seq":N,"cmd":NAME,<args>}``
    telemetry : ``{"seq":N,"tlm":TYPE,<fields>}``
    ack/nak   : ``{"seq":N,"ack":true}`` / ``{"seq":N,"nak":REASON}``

The CRC-8 (poly 0x07, init 0x00) guards the ASCII framing against serial/UART bit
errors; JSON relies on the transport's own integrity (TCP/BLE checksums). A malformed
frame raises :class:`DecodeError` (never an unexpected exception — the decoder is
fuzz-hardened), so the receiver can NAK and move on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Positional argument schemas for the ASCII framing (the JSON framing carries names).
COMMAND_ARGS: dict[str, list[str]] = {
    "drive": ["v", "w"],
    "motor": ["id", "pwm"],
    "servo": ["id", "deg"],
    "stop": [],
    "estop": [],
    "ping": [],
    "set": ["param", "value"],
    # Robot-arm joint control — mirrored in firmware/pibot_arm_stm32 (docs/plans/
    # 2026-06-13-pibot-arm-control.md). `id` selects the joint; the value is degrees (jpos),
    # degrees/sec (jvel), or a flag (enable).
    "jpos": ["id", "deg"],
    "jmove": ["id", "deg", "dps"],  # move to angle at a host-set speed (deg/sec)
    "jvel": ["id", "dps"],
    "jstop": ["id"],
    "home": ["id"],
    "enable": ["on"],
    # Robot-arm end-effector (M-ARM-2) — servo gripper on the spare E0 channel + an optional
    # digital-output tool (relay/pneumatic). `grip` is an absolute servo angle (deg); `tool` a flag.
    "grip": ["deg"],
    "tool": ["on"],
}

TELEMETRY_FIELDS: dict[str, list[str]] = {
    "state": ["v", "w"],
    "battery": ["volts"],
    "current": ["amps"],
    "encoder": ["left", "right"],
    "imu": ["ax", "ay", "az", "gx", "gy", "gz"],
    "range": ["mm"],
    "event": ["code"],
    # Gripper telemetry (M-ARM-2): servo angle (deg) + tool digital-output state (0/1).
    "grip": ["deg", "tool"],
}


class MessageType(StrEnum):
    COMMAND = "command"
    TELEMETRY = "telemetry"
    ACK = "ack"
    NAK = "nak"


@dataclass
class Message:
    """One logical protocol message, independent of wire encoding."""

    type: MessageType
    seq: int
    name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    reason: str = ""  # NAK only


class DecodeError(Exception):
    """A frame could not be decoded. ``reason`` is a short machine code."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def crc8(data: bytes) -> int:
    """CRC-8 (polynomial 0x07, init 0x00) over ``data``."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


class SeqTracker:
    """8-bit sequence numbering: monotonic-with-wrap and dup/order detection."""

    def __init__(self) -> None:
        self._next = 0
        self._last: int | None = None

    def next(self) -> int:
        seq = self._next
        self._next = (self._next + 1) & 0xFF
        return seq

    def observe(self, seq: int) -> str:
        """Classify an incoming ``seq`` as ``ok`` / ``duplicate`` / ``out_of_order``."""
        if self._last is None:
            self._last = seq
            return "ok"
        if seq == self._last:
            return "duplicate"
        expected = (self._last + 1) & 0xFF
        self._last = seq
        return "ok" if seq == expected else "out_of_order"


# ---- value formatting ----------------------------------------------------


def _fmt(value: Any) -> str:
    if isinstance(value, bool):  # avoid bool-is-int surprises
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)  # repr round-trips a Python float exactly
    return str(value)


def _parse_token(token: str) -> Any:
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token


# ---- public API ----------------------------------------------------------


def encode(msg: Message, encoding: str = "ascii") -> bytes:
    """Serialize a :class:`Message` to a single framed line (with trailing newline)."""
    if encoding == "json":
        return _encode_json(msg)
    if encoding == "ascii":
        return _encode_ascii(msg)
    raise ValueError(f"unknown encoding: {encoding!r}")


def decode(frame: bytes | str, encoding: str = "ascii") -> Message:
    """Parse one framed line into a :class:`Message`, or raise :class:`DecodeError`."""
    if isinstance(frame, bytes):
        try:
            text = frame.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DecodeError("encoding") from exc
    else:
        text = frame
    text = text.strip("\r\n")
    if encoding == "json":
        return _decode_json(text)
    if encoding == "ascii":
        return _decode_ascii(text)
    raise ValueError(f"unknown encoding: {encoding!r}")


# ---- ASCII ---------------------------------------------------------------


def _schema_for(msg: Message) -> list[str] | None:
    if msg.type is MessageType.COMMAND:
        return COMMAND_ARGS.get(msg.name)
    return TELEMETRY_FIELDS.get(msg.name)


def _encode_ascii(msg: Message) -> bytes:
    if msg.type is MessageType.ACK:
        return f"ACK {msg.seq}\n".encode()
    if msg.type is MessageType.NAK:
        return f"NAK {msg.seq} {msg.reason}\n".encode()
    marker = ">" if msg.type is MessageType.COMMAND else "<"
    schema = _schema_for(msg)
    if schema is not None:
        values = [msg.args[k] for k in schema]
    else:
        values = list(msg.args.values())
    payload = ",".join([str(msg.seq), msg.name, *[_fmt(v) for v in values]])
    return f"{marker}{payload}*{crc8(payload.encode()):02X}\n".encode()


def _decode_ascii(text: str) -> Message:
    if not text:
        raise DecodeError("empty")
    if text.startswith("ACK "):
        return Message(MessageType.ACK, _parse_seq(text[4:].strip()))
    if text.startswith("NAK "):
        rest = text[4:].split(" ", 1)
        reason = rest[1] if len(rest) > 1 else ""
        return Message(MessageType.NAK, _parse_seq(rest[0]), reason=reason)
    if text[0] not in (">", "<"):
        raise DecodeError("marker")
    if "*" not in text:
        raise DecodeError("frame")
    body, _, crc_hex = text.rpartition("*")
    payload = body[1:]
    try:
        expected = int(crc_hex, 16)
    except ValueError as exc:
        raise DecodeError("crc") from exc
    if crc8(payload.encode()) != expected:
        raise DecodeError("crc")
    parts = payload.split(",")
    if len(parts) < 2:
        raise DecodeError("fields")
    seq = _parse_seq(parts[0])
    name = parts[1]
    tokens = parts[2:]
    mtype = MessageType.COMMAND if text[0] == ">" else MessageType.TELEMETRY
    schema = COMMAND_ARGS.get(name) if mtype is MessageType.COMMAND else TELEMETRY_FIELDS.get(name)
    if schema is not None:
        if len(tokens) != len(schema):
            raise DecodeError("arity")
        args = {schema[i]: _parse_token(tokens[i]) for i in range(len(schema))}
    else:
        args = {f"arg{i}": _parse_token(tok) for i, tok in enumerate(tokens)}
    return Message(mtype, seq, name, args)


def _parse_seq(token: str) -> int:
    try:
        seq = int(token)
    except ValueError as exc:
        raise DecodeError("seq") from exc
    if not 0 <= seq <= 255:
        raise DecodeError("seq")
    return seq


# ---- JSON ----------------------------------------------------------------


def _encode_json(msg: Message) -> bytes:
    if msg.type is MessageType.ACK:
        obj: dict[str, Any] = {"seq": msg.seq, "ack": True}
    elif msg.type is MessageType.NAK:
        obj = {"seq": msg.seq, "nak": msg.reason}
    elif msg.type is MessageType.COMMAND:
        obj = {"seq": msg.seq, "cmd": msg.name, **msg.args}
    else:
        obj = {"seq": msg.seq, "tlm": msg.name, **msg.args}
    return (json.dumps(obj) + "\n").encode()


def _decode_json(text: str) -> Message:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DecodeError("json") from exc
    if not isinstance(obj, dict) or "seq" not in obj:
        raise DecodeError("schema")
    seq = obj["seq"]
    if not isinstance(seq, int) or isinstance(seq, bool):
        raise DecodeError("seq")
    if "cmd" in obj:
        args = {k: v for k, v in obj.items() if k not in ("seq", "cmd")}
        return Message(MessageType.COMMAND, seq, str(obj["cmd"]), args)
    if "tlm" in obj:
        args = {k: v for k, v in obj.items() if k not in ("seq", "tlm")}
        return Message(MessageType.TELEMETRY, seq, str(obj["tlm"]), args)
    if "ack" in obj:
        return Message(MessageType.ACK, seq)
    if "nak" in obj:
        return Message(MessageType.NAK, seq, reason=str(obj["nak"]))
    raise DecodeError("schema")
