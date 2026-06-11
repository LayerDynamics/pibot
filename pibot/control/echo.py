"""Host-side mirror of the Arduino firmware's protocol behaviour.

:class:`EchoResponder` decodes incoming frames exactly as the firmware does and replies
the same way — ACK every command, answer ``ping`` with a telemetry frame, NAK a corrupt
frame. It is the no-hardware CI stand (``tests/test_echo_roundtrip.py``) and doubles as
a dev peer so the control path can be exercised without a wired Arduino. The reference
firmware (``firmware/pibot_arduino``) implements the same contract in C++.
"""

from __future__ import annotations

from pibot.protocol.codec import (
    DecodeError,
    Message,
    MessageType,
    SeqTracker,
    decode,
    encode,
)
from pibot.transport.base import FrameBuffer


class EchoResponder:
    """Reassemble a byte stream into frames and produce the firmware's responses."""

    def __init__(self, encoding: str = "ascii") -> None:
        self._encoding = encoding
        self._buf = FrameBuffer()
        self._tlm_seq = SeqTracker()

    def feed(self, data: bytes) -> list[bytes]:
        """Feed received bytes; return the list of encoded response frames to send back."""
        self._buf.feed(data)
        out: list[bytes] = []
        while (frame := self._buf.next_frame()) is not None:
            out.extend(self._handle(frame))
        return out

    def _handle(self, frame: bytes) -> list[bytes]:
        try:
            msg = decode(frame, self._encoding)
        except DecodeError as exc:
            return [encode(Message(MessageType.NAK, 0, reason=exc.reason), self._encoding)]

        if msg.type is not MessageType.COMMAND:
            return []  # the firmware only acts on commands

        responses = [encode(Message(MessageType.ACK, msg.seq), self._encoding)]
        if msg.name == "ping":
            responses.append(
                encode(
                    Message(
                        MessageType.TELEMETRY, self._tlm_seq.next(), "battery", {"volts": 12.4}
                    ),
                    self._encoding,
                )
            )
        return responses
