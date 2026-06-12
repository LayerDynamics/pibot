"""I2C transport — drive the robot over the Pi's I²C bus (the microcontroller is an
I²C slave at a fixed address).

SMBus block transfers cap at 32 bytes, so a protocol frame (JSON-lines telemetry can
exceed that) is split across multiple block writes on ``send`` and reassembled from
block reads on ``recv`` via the shared :class:`FrameBuffer` until a newline. The agent
is the bus's sole master, so there is no contention. Any bus :class:`OSError` drops the
link (``is_open`` -> False) so the deadman watchdog stops the robot — wireless-grade
fail-safe applied to the wire bus too.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from pibot.transport.base import FrameBuffer, Transport, TransportError

_BLOCK = 32  # SMBus block transfer maximum
DEFAULT_REGISTER = 0x01


class I2CTransport(Transport):
    def __init__(
        self,
        bus: int = 1,
        address: int = 0x08,
        *,
        register: int = DEFAULT_REGISTER,
        bus_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._bus_num = bus
        self._address = address
        self._register = register
        self._bus: Any | None = None
        self._buf = FrameBuffer()
        self._last_frame_ms: float | None = None
        self._bus_factory = bus_factory or self._default_factory

    def _default_factory(self) -> Any:
        import smbus2  # Linux-only; imported lazily so the host CLI/tests don't need it

        return smbus2.SMBus(self._bus_num)

    def open(self) -> None:
        if self._bus is None:
            self._bus = self._bus_factory()
        self._buf.clear()

    def close(self) -> None:
        if self._bus is not None:
            try:
                self._bus.close()
            finally:
                self._bus = None

    def _drop(self) -> None:
        self.close()

    def send(self, frame: bytes) -> None:
        if self._bus is None:
            raise TransportError("i2c transport not open")
        try:
            for start in range(0, len(frame), _BLOCK):
                chunk = list(frame[start : start + _BLOCK])
                self._bus.write_i2c_block_data(self._address, self._register, chunk)
        except OSError as exc:
            self._drop()  # bus error -> fail safe
            raise TransportError(f"i2c send failed: {exc}") from exc

    def recv(self, timeout: float) -> bytes | None:
        if self._bus is None:
            raise TransportError("i2c transport not open")
        deadline = time.monotonic() + timeout
        while True:
            frame = self._buf.next_frame()
            if frame is not None:
                self._last_frame_ms = time.monotonic() * 1000
                return frame
            try:
                block = self._bus.read_i2c_block_data(self._address, self._register, _BLOCK)
            except OSError:
                self._drop()  # bus error -> fail safe
                return None
            data = bytes(block).rstrip(b"\x00")  # slave pads short reads with 0x00
            if data:
                self._buf.feed(data)
                continue
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.001)

    @property
    def is_open(self) -> bool:
        return self._bus is not None

    @property
    def info(self) -> dict[str, Any]:
        return {
            "backend": "i2c",
            "bus": self._bus_num,
            "address": self._address,
            "register": self._register,
            "open": self.is_open,
            "last_frame_ms": self._last_frame_ms,
        }
