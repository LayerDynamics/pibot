"""Pi↔Arduino wire protocol — framing codec shared by host, agent, and firmware.

Two interoperable encodings (SPEC-1 §6.4): a compact CRC-checked ASCII framing for
constrained MCUs (AVR over noisy serial/UART) and a JSON-lines variant for capable
MCUs (ESP32 over TCP). Both decode to one :class:`~pibot.protocol.codec.Message` type.
"""

from __future__ import annotations

from pibot.protocol.codec import (
    DecodeError,
    Message,
    MessageType,
    SeqTracker,
    crc8,
    decode,
    encode,
)

__all__ = [
    "DecodeError",
    "Message",
    "MessageType",
    "SeqTracker",
    "crc8",
    "decode",
    "encode",
]
