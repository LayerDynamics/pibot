"""Teleop cadence keeper: re-sends the last drive command at a fixed rate.

The ``pibotd`` deadman stops the robot if no drive arrives within ``watchdog_ms``.
The cadence keeper solves this: after each GUI drive command the sidecar keeps
re-sending it so the deadman stays fed, even if the user's finger is motionless
on the keyboard.  Sending ``stop`` (or any non-drive command) clears the pending
command so the repeat loop idles.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any


SendFn = Callable[[str, dict[str, Any]], Awaitable[None]]


class CadenceKeeper:
    """Re-sends the last ``drive`` command at *rate_hz* until cleared or stopped."""

    def __init__(self, rate_hz: float = 20) -> None:
        self._period = 1.0 / rate_hz if rate_hz > 0 else 0.05
        self._last: tuple[str, dict[str, Any]] | None = None
        self._send: SendFn | None = None
        self._task: asyncio.Task[None] | None = None

    def update(self, cmd: str, args: dict[str, Any]) -> None:
        """Record the latest command.  Only ``drive`` is repeated; any other command clears."""
        if cmd == "drive":
            self._last = (cmd, args)
        else:
            self._last = None

    def start(self, send_fn: SendFn) -> None:
        """Begin the repeat loop, calling *send_fn(cmd, args)* each tick."""
        self._send = send_fn
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the repeat loop."""
        self._last = None
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._period)
                if self._last is not None and self._send is not None:
                    cmd, args = self._last
                    with contextlib.suppress(Exception):
                        await self._send(cmd, args)
        except asyncio.CancelledError:
            pass
