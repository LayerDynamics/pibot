"""``WS /api/video`` — relay the robot's MJPEG stream to the webview (SPEC-3 FR-6/FR-9)."""

from __future__ import annotations

import asyncio
import contextlib

from aiohttp import web

from pibot.mc.state import STATE


async def handle_video_ws(request: web.Request) -> web.StreamResponse:
    """Forward header+JPEG pairs from the robot relay to the webview."""
    state = request.app[STATE]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    relay = getattr(state, "video_relay", None)
    if relay is None:
        await ws.close()
        return ws

    q = relay.subscribe()

    async def _push() -> None:
        try:
            while not ws.closed:
                try:
                    hdr, jpeg = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                await ws.send_str(hdr)
                await ws.send_bytes(jpeg)
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            relay.unsubscribe(q)
            if not ws.closed:
                with contextlib.suppress(Exception):
                    await ws.close()

    pusher = asyncio.create_task(_push())
    try:
        async for msg in ws:
            if msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSING, web.WSMsgType.ERROR):
                break
    finally:
        pusher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pusher
    return ws


def add_video_routes(app: web.Application) -> None:
    app.router.add_get("/api/video", handle_video_ws)
