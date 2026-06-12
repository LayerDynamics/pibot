"""Serial transport (pyserial) — USB ``/dev/ttyACM*``, GPIO ``/dev/serial0``, and
(in M5) Bluetooth ``/dev/rfcomm*`` all share this one code path.

Opens the port non-blocking (``timeout=0``) and polls in ``recv`` so a deadline is
honoured precisely; the shared :class:`FrameBuffer` reassembles partial reads into
whole frames. ``pyserial``'s ``loop://`` URL is accepted too, which the tests use to
exercise the real serial API without hardware.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from pibot.transport.base import FrameBuffer, Transport, TransportError


class SerialTransport(Transport):
    def __init__(
        self,
        port: str,
        baud: int = 115200,
        *,
        serial_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._port = port
        self._baud = baud
        self._serial: Any | None = None
        self._buf = FrameBuffer()
        self._last_frame_ms: float | None = None
        self._serial_factory = serial_factory or self._default_factory

    def _default_factory(self) -> Any:
        import serial

        return serial.serial_for_url(self._port, baudrate=self._baud, timeout=0)

    def open(self) -> None:
        if self._serial is None:
            self._serial = self._serial_factory()
        self._buf.clear()

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None

    def send(self, frame: bytes) -> None:
        if self._serial is None:
            raise TransportError("serial transport not open")
        self._serial.write(frame)

    def recv(self, timeout: float) -> bytes | None:
        if self._serial is None:
            raise TransportError("serial transport not open")
        deadline = time.monotonic() + timeout
        while True:
            frame = self._buf.next_frame()
            if frame is not None:
                self._last_frame_ms = time.monotonic() * 1000
                return frame
            try:
                waiting = self._serial.in_waiting
            except (OSError, AttributeError):
                waiting = 0
            chunk = self._serial.read(waiting or 1)
            if chunk:
                self._buf.feed(chunk)
                continue
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.001)

    @property
    def is_open(self) -> bool:
        return self._serial is not None and bool(self._serial.is_open)

    @property
    def info(self) -> dict[str, Any]:
        return {
            "backend": "serial",
            "port": self._port,
            "baud": self._baud,
            "open": self.is_open,
            "last_frame_ms": self._last_frame_ms,
        }
