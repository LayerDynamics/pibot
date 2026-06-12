"""The agent's transport controller — the SINGLE owner of the link to the robot.

All commands flow through :meth:`submit`, serialized by a lock so frames never interleave
on the wire (the plan's "single serialized command queue"). A background reader routes
ACK/NAK frames back to the awaiting caller and telemetry frames to a callback; a ticker
drives the deadman watchdog. ``estop`` preempts — it asserts a stop immediately, outside
the normal queue. The blocking transport ``recv`` is bridged into asyncio via a thread.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from agent.safety import AgentSafety
from pibot.control.safety import Limits
from pibot.protocol.codec import (
    DecodeError,
    Message,
    MessageType,
    SeqTracker,
    decode,
)
from pibot.transport.base import Transport

TelemetryFn = Callable[[Message], None]


class ControlRejected(Exception):
    """A command was rejected by the safety layer before reaching the wire."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class TransportController:
    def __init__(
        self,
        transport: Transport,
        *,
        limits: Limits | None = None,
        deadman_ms: float = 300,
        max_rate_hz: float = 50,
        encoding: str = "ascii",
        on_telemetry: TelemetryFn | None = None,
        poll_interval: float = 0.02,
        tick_interval: float = 0.05,
    ) -> None:
        self._transport = transport
        self._encoding = encoding
        self._safety = AgentSafety(
            transport.send,
            limits=limits,
            deadman_ms=deadman_ms,
            max_rate_hz=max_rate_hz,
            encoding=encoding,
        )
        self._on_telemetry = on_telemetry
        self._poll = poll_interval
        self._tick = tick_interval
        self._seq = SeqTracker()
        self._acks: dict[int, asyncio.Future[Message]] = {}
        self._lock = asyncio.Lock()
        self._running = False
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if not self._transport.is_open:
            self._transport.open()
        self._running = True
        self._tasks = [
            asyncio.create_task(self._reader()),
            asyncio.create_task(self._ticker()),
        ]

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self._transport.close()

    async def submit(self, msg: Message, *, timeout: float = 1.0) -> Message:
        """Send one command (serialized + safety-gated) and return its ACK/NAK reply."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Message] = loop.create_future()
        async with self._lock:
            seq = self._seq.next()
            outgoing = Message(msg.type, seq, msg.name, dict(msg.args), msg.reason)
            self._acks[seq] = fut
            sent, reason = self._safety.submit(outgoing)
        if not sent:
            self._acks.pop(seq, None)
            raise ControlRejected(reason)
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._acks.pop(seq, None)

    def estop(self) -> None:
        """Preempt: latch e-stop and command a stop immediately."""
        self._safety.trip_estop()

    def resume(self) -> None:
        self._safety.resume()

    @property
    def latched(self) -> bool:
        return self._safety.latched

    @property
    def transport_info(self) -> dict[str, Any]:
        return self._transport.info

    async def _reader(self) -> None:
        try:
            while self._running:
                frame = await asyncio.to_thread(self._transport.recv, self._poll)
                if frame is None:
                    continue
                try:
                    msg = decode(frame, self._encoding)
                except DecodeError:
                    continue
                if msg.type in (MessageType.ACK, MessageType.NAK):
                    fut = self._acks.get(msg.seq)
                    if fut is not None and not fut.done():
                        fut.set_result(msg)
                elif msg.type is MessageType.TELEMETRY and self._on_telemetry is not None:
                    self._on_telemetry(msg)
        except asyncio.CancelledError:
            pass

    async def _ticker(self) -> None:
        try:
            while self._running:
                self._safety.tick()
                await asyncio.sleep(self._tick)
        except asyncio.CancelledError:
            pass
