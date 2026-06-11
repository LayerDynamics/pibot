"""RFCOMM transport — drive the robot over Bluetooth Classic.

Once ``rfcomm bind`` attaches the remote device to ``/dev/rfcomm0``, it is just a
serial port, so this is a thin :class:`SerialTransport` specialisation: same framing,
same reassembly, same (now fail-safe) read path. The only additions are the default
device node, ``rfcomm`` backend/address in ``info``, and the bind/release argv builders.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pibot.transport.serial import SerialTransport

DEFAULT_PORT = "/dev/rfcomm0"


class RfcommTransport(SerialTransport):
    def __init__(
        self,
        port: str = DEFAULT_PORT,
        baud: int = 115200,
        *,
        address: str | None = None,
        channel: int = 1,
        serial_factory: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(port, baud, serial_factory=serial_factory)
        self._address = address
        self._channel = channel

    @property
    def info(self) -> dict[str, Any]:
        base = super().info
        base["backend"] = "rfcomm"
        base["address"] = self._address
        base["channel"] = self._channel
        return base


def bind_command(address: str, *, channel: int = 1, dev: int = 0) -> list[str]:
    """argv to bind a remote BT device to ``/dev/rfcomm<dev>`` (``rfcomm bind``)."""
    return ["rfcomm", "bind", str(dev), address, str(channel)]


def release_command(*, dev: int = 0) -> list[str]:
    """argv to release a previously-bound ``/dev/rfcomm<dev>`` (``rfcomm release``)."""
    return ["rfcomm", "release", str(dev)]
