"""The Transport abstraction and the shared frame-reassembly buffer.

A transport carries opaque newline-delimited protocol frames. Backends read arbitrary
byte chunks off the wire; :class:`FrameBuffer` turns that stream back into whole frames
so ``recv`` always returns one complete frame (or ``None``).
"""

from __future__ import annotations

import abc
from typing import Any


class TransportError(Exception):
    """A transport operation failed (not open, link dropped, I/O error)."""


class FrameBuffer:
    """Reassemble a byte stream into newline-delimited frames."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> None:
        self._buf.extend(data)

    def next_frame(self) -> bytes | None:
        """Pop the next complete frame (including its trailing ``\\n``), or None."""
        idx = self._buf.find(b"\n")
        if idx < 0:
            return None
        line = bytes(self._buf[: idx + 1])
        del self._buf[: idx + 1]
        return line

    def clear(self) -> None:
        self._buf.clear()


class Transport(abc.ABC):
    """A bidirectional, frame-oriented link to the robot's microcontroller."""

    @abc.abstractmethod
    def open(self) -> None:
        """Open the link. Idempotent-safe to call once before use."""

    @abc.abstractmethod
    def close(self) -> None:
        """Close the link and release resources."""

    @abc.abstractmethod
    def send(self, frame: bytes) -> None:
        """Transmit one already-encoded protocol frame."""

    @abc.abstractmethod
    def recv(self, timeout: float) -> bytes | None:
        """Return one complete frame, or ``None`` if none arrived within ``timeout``."""

    @property
    @abc.abstractmethod
    def is_open(self) -> bool:
        """Whether the link is currently open and healthy."""

    @property
    @abc.abstractmethod
    def info(self) -> dict[str, Any]:
        """Backend name, endpoint, and health (e.g. ``last_frame_ms``)."""
