"""A no-hardware transport whose peer is the firmware-mirror :class:`EchoResponder`.

Sending a command yields the firmware's ACK/telemetry on ``recv``, so the whole control
path (``pibot cmd``, the M4 agent) can run with no Arduino attached — for tests and for
``--transport responder`` dev runs. Sent frames are recorded in ``sent`` for inspection.
"""

from __future__ import annotations

from typing import Any

from pibot.control.echo import EchoResponder
from pibot.transport.base import FrameBuffer, Transport, TransportError


class ResponderTransport(Transport):
    def __init__(self, encoding: str = "ascii") -> None:
        self._open = False
        self._rx = FrameBuffer()
        self._responder = EchoResponder(encoding)
        self.sent: list[bytes] = []

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def send(self, frame: bytes) -> None:
        if not self._open:
            raise TransportError("responder transport not open")
        self.sent.append(frame)
        for out in self._responder.feed(frame):
            self._rx.feed(out)

    def recv(self, timeout: float) -> bytes | None:
        if not self._open:
            raise TransportError("responder transport not open")
        return self._rx.next_frame()

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def info(self) -> dict[str, Any]:
        return {"backend": "responder", "open": self._open}
