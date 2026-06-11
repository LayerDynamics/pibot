"""BLE transport — drive the robot over Bluetooth Low Energy (Nordic-UART style).

bleak is async and the :class:`Transport` contract is synchronous, so this backend owns
a private asyncio event loop running in a daemon thread; ``open``/``send``/``close`` are
bridged onto it with :func:`asyncio.run_coroutine_threadsafe`. Peripheral notifications
arrive on the loop thread and are pushed onto a thread-safe queue that ``recv`` drains
(reassembling partial packets via :class:`FrameBuffer`). A radio drop — bleak's
``disconnected_callback`` or any GATT error — marks the link down so the M4 deadman
watchdog stops the robot; a wireless link is never trusted to stay up.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from pibot.transport.base import FrameBuffer, Transport, TransportError

# Nordic UART Service (NUS) characteristic UUIDs.
NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # central writes commands here
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # peripheral notifies telemetry here

ClientFactory = Callable[[str, Callable[[Any], None]], Any]


class BleTransport(Transport):
    def __init__(
        self,
        address: str,
        *,
        rx: str = NUS_RX,
        tx: str = NUS_TX,
        client_factory: ClientFactory | None = None,
        connect_timeout: float = 10.0,
    ) -> None:
        self._address = address
        self._rx = rx
        self._tx = tx
        self._connect_timeout = connect_timeout
        self._client_factory = client_factory or self._default_factory
        self._client: Any | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._buf = FrameBuffer()
        self._connected = False
        self._last_frame_ms: float | None = None

    def _default_factory(self, address: str, on_disconnect: Callable[[Any], None]) -> Any:
        from bleak import BleakClient  # Pi-only dep; imported lazily

        return BleakClient(address, disconnected_callback=on_disconnect)

    # ---- event-loop thread bridge ----------------------------------------

    def _start_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def _run(self, coro: Any) -> Any:
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(self._connect_timeout)

    def _on_notify(self, _sender: Any, data: bytearray) -> None:
        self._queue.put(bytes(data))

    def _on_disconnect(self, _client: Any) -> None:
        self._connected = False  # radio dropped -> recv will fail safe

    # ---- Transport contract ----------------------------------------------

    def open(self) -> None:
        if self._loop is None:
            self._start_loop()
        self._buf.clear()

        async def _connect() -> None:
            self._client = self._client_factory(self._address, self._on_disconnect)
            await self._client.connect()
            await self._client.start_notify(self._tx, self._on_notify)
            self._connected = True

        self._run(_connect())

    def close(self) -> None:
        if self._client is not None and self._loop is not None and self._connected:
            try:
                self._run(self._client.disconnect())
            except Exception:  # noqa: BLE001 - teardown is best-effort
                pass
        self._teardown()

    def _teardown(self) -> None:
        self._connected = False
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=2.0)
            self._loop.close()
            self._loop = None
            self._thread = None
        self._client = None

    def send(self, frame: bytes) -> None:
        if not self._connected or self._client is None:
            raise TransportError("ble transport not open")
        try:
            self._run(self._client.write_gatt_char(self._rx, frame, response=False))
        except Exception as exc:  # noqa: BLE001 - any GATT error is a dropped link
            self._connected = False
            raise TransportError(f"ble send failed: {exc}") from exc

    def recv(self, timeout: float) -> bytes | None:
        if self._loop is None:
            raise TransportError("ble transport not open")
        deadline = time.monotonic() + timeout
        while True:
            frame = self._buf.next_frame()
            if frame is not None:
                self._last_frame_ms = time.monotonic() * 1000
                return frame
            if not self._connected and self._queue.empty():
                return None  # link dropped and nothing buffered -> fail safe
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                data = self._queue.get(timeout=min(remaining, 0.05))
            except queue.Empty:
                continue
            self._buf.feed(data)

    @property
    def is_open(self) -> bool:
        return self._connected

    @property
    def info(self) -> dict[str, Any]:
        return {
            "backend": "ble",
            "address": self._address,
            "open": self.is_open,
            "last_frame_ms": self._last_frame_ms,
        }
