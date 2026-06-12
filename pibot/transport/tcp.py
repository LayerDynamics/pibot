"""TCP transport — the Pi talks to a Wi-Fi bridge or an ESP32 running the firmware
over a TCP socket. Same framing/reassembly as serial; stdlib ``socket`` only.

Fail-safe is first-class: a dropped connection (peer close or I/O error) marks the
transport down (``is_open`` -> False) and ``recv`` returns ``None``, so the agent's
deadman watchdog (M4) stops the robot. A wireless link is never trusted to stay up.
"""

from __future__ import annotations

import select
import socket
import time
from typing import Any

from pibot.transport.base import FrameBuffer, Transport, TransportError


class TcpTransport(Transport):
    def __init__(self, host: str, port: int, *, connect_timeout: float = 5.0) -> None:
        self._host = host
        self._port = port
        self._connect_timeout = connect_timeout
        self._sock: socket.socket | None = None
        self._buf = FrameBuffer()
        self._last_frame_ms: float | None = None

    def open(self) -> None:
        sock = socket.create_connection((self._host, self._port), timeout=self._connect_timeout)
        sock.setblocking(False)
        self._sock = sock
        self._buf.clear()

    def close(self) -> None:
        self._drop()

    def _drop(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def send(self, frame: bytes) -> None:
        if self._sock is None:
            raise TransportError("tcp transport not open")
        try:
            self._sock.sendall(frame)
        except OSError as exc:
            self._drop()
            raise TransportError(f"tcp send failed: {exc}") from exc

    def recv(self, timeout: float) -> bytes | None:
        if self._sock is None:
            raise TransportError("tcp transport not open")
        deadline = time.monotonic() + timeout
        while True:
            frame = self._buf.next_frame()
            if frame is not None:
                self._last_frame_ms = time.monotonic() * 1000
                return frame
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([self._sock], [], [], remaining)
            if not ready:
                return None
            try:
                data = self._sock.recv(4096)
            except BlockingIOError:
                continue
            except OSError:
                self._drop()  # link error -> fail safe
                return None
            if data == b"":  # peer closed the connection
                self._drop()
                return None
            self._buf.feed(data)

    @property
    def is_open(self) -> bool:
        return self._sock is not None

    @property
    def info(self) -> dict[str, Any]:
        return {
            "backend": "tcp",
            "host": self._host,
            "port": self._port,
            "open": self.is_open,
            "last_frame_ms": self._last_frame_ms,
        }
