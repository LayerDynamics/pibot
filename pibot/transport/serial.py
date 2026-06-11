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
            try:
                chunk = self._serial.read(waiting or 1)
            except OSError:
                self.close()  # device/link dropped (USB unplug, RFCOMM link loss) -> fail safe
                return None
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


# ---- GPIO-UART finalization (T5.5) ---------------------------------------

DEFAULT_UART_PORT = "/dev/serial0"

UART_SETUP_DOC = """GPIO-UART wiring (Pi <-> microcontroller):

  - Enable the primary UART: set ``enable_uart=1`` in /boot/firmware/config.txt
    (and free it from the login console: ``console=serial0`` removed from cmdline.txt),
    so ``/dev/serial0`` is the wired UART, not Bluetooth.
  - Cross TX<->RX and share a common ground.
  - LEVEL SHIFTER REQUIRED: the Pi's GPIO UART is 3.3 V tolerant only. A 5 V device
    (classic Arduino) MUST go through a 3.3 V <-> 5 V level shifter (or a divider on the
    Pi RX line) — feeding 5 V into a Pi GPIO pin can destroy it. A 3.3 V microcontroller
    (ESP32) wires directly.
"""


def uart_transport(
    baud: int = 115200,
    *,
    serial_factory: Callable[[], Any] | None = None,
) -> SerialTransport:
    """A :class:`SerialTransport` bound to the Pi's GPIO UART (``/dev/serial0``)."""
    return SerialTransport(DEFAULT_UART_PORT, baud, serial_factory=serial_factory)
