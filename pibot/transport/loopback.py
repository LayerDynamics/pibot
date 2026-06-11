"""In-memory loopback transport — a test double and a no-hardware dev backend.

Bytes written with :meth:`send` (or injected with :meth:`feed_raw`) are reassembled by
the shared :class:`FrameBuffer` and returned by :meth:`recv`, so it exercises the same
framing contract as the real serial/TCP backends without any hardware.
"""

from __future__ import annotations

from typing import Any

from pibot.transport.base import FrameBuffer, Transport, TransportError


class LoopbackTransport(Transport):
    def __init__(self) -> None:
        self._open = False
        self._buf = FrameBuffer()

    def open(self) -> None:
        self._open = True
        self._buf.clear()

    def close(self) -> None:
        self._open = False

    def _require_open(self) -> None:
        if not self._open:
            raise TransportError("transport not open")

    def send(self, frame: bytes) -> None:
        self._require_open()
        self._buf.feed(frame)

    def feed_raw(self, data: bytes) -> None:
        """Inject raw (possibly partial) bytes into the receive buffer (test/dev aid)."""
        self._require_open()
        self._buf.feed(data)

    def recv(self, timeout: float) -> bytes | None:
        self._require_open()
        return self._buf.next_frame()

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def info(self) -> dict[str, Any]:
        return {"backend": "loopback", "open": self._open}
