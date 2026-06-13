"""Sidecar video relay: consume pibotd ``WS /video`` → fan out to ``WS /api/video`` clients.

``VideoRelay`` opens one connection to the robot's ``/video`` endpoint and fans each
header+binary frame pair to a bounded per-subscriber queue.  A slow ``/api/video``
consumer drops frames (drop-oldest) and never backpressures the source or the relay
task.  The relay task is independent of the telemetry and control sockets — closing
one ``/api/video`` session cannot affect either of those streams.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any


class VideoRelay:
    """One upstream /video WS connection, N downstream /api/video subscriber queues."""

    MAXSIZE = 4  # frames held per subscriber before drop-oldest

    def __init__(self, session: Any, video_url: str) -> None:
        """
        Args:
            session:    An ``aiohttp.ClientSession`` (owned externally).
            video_url:  Full URL of the robot's ``WS /video`` endpoint.
        """
        self._session = session
        self._url = video_url
        self._subscribers: list[asyncio.Queue[tuple[str, bytes]]] = []
        self._task: asyncio.Task[None] | None = None

    def subscribe(self) -> asyncio.Queue[tuple[str, bytes]]:
        """Return a queue that receives ``(json_header_str, jpeg_bytes)`` tuples."""
        q: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue(maxsize=self.MAXSIZE)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[tuple[str, bytes]]) -> None:
        with contextlib.suppress(ValueError):
            self._subscribers.remove(q)

    def start(self) -> None:
        """Start the upstream receive task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Cancel the relay task."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _push(self, hdr: str, jpeg: bytes) -> None:
        for q in list(self._subscribers):
            if q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait((hdr, jpeg))

    async def _loop(self) -> None:
        import aiohttp

        try:
            async with self._session.ws_connect(self._url) as ws:
                pending_hdr: str | None = None
                async for msg in ws:
                    if msg.type is aiohttp.WSMsgType.TEXT:
                        pending_hdr = msg.data
                    elif msg.type is aiohttp.WSMsgType.BINARY:
                        if pending_hdr is not None:
                            self._push(pending_hdr, msg.data)
                            pending_hdr = None
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSING,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
