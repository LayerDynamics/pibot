"""``/api/connect`` · ``/api/disconnect`` · ``WS /api/telemetry`` — the robot link + the
relayed telemetry stream (SPEC-3 FR-3, FR-5).

The telemetry WS forwards ``pibotd`` snapshot frames straight through to the webview; later
milestones tee the same stream into the metrics + session recorders (M12.4).
"""

from __future__ import annotations

import asyncio
import contextlib

from aiohttp import web

from pibot.errors import InventoryError
from pibot.mc.state import STATE


async def handle_connect(request: web.Request) -> web.Response:
    state = request.app[STATE]
    data = await request.json()
    robot = data.get("robot")
    if not robot:
        raise web.HTTPBadRequest(text="robot required")
    assert state.link is not None
    try:
        info = await state.link.connect(str(robot))
    except InventoryError as exc:
        raise web.HTTPNotFound(text=str(exc)) from exc
    except (OSError, web.HTTPException) as exc:
        raise web.HTTPBadGateway(text=f"could not reach {robot}: {exc}") from exc
    state.connected = True
    state.robot = state.link.robot
    state.video_relay = state.link.video_relay
    return web.json_response(info, status=201)


async def handle_disconnect(request: web.Request) -> web.Response:
    state = request.app[STATE]
    if state.link is not None:
        await state.link.disconnect()
    state.connected = False
    state.robot = None
    return web.json_response({"disconnected": True})


async def handle_telemetry_ws(request: web.Request) -> web.StreamResponse:
    state = request.app[STATE]
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    if state.link is None or not state.link.connected:
        await ws.send_json({"error": "not connected"})
        await ws.close()
        return ws

    link = state.link

    async def _pump() -> None:
        # Forward pibotd snapshots until the upstream ends, the client closes, or cancelled.
        try:
            async for snap in link.telemetry_stream():
                if ws.closed:
                    break
                await ws.send_json(snap)
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            # Upstream ended/dropped -> close the webview side so the client unblocks.
            if not ws.closed:
                with contextlib.suppress(Exception):
                    await ws.close()

    pump = asyncio.create_task(_pump())
    try:
        # Read incoming frames so a client-initiated CLOSE completes the handshake
        # (a send-only handler would deadlock the client's close()).
        async for msg in ws:
            if msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSING, web.WSMsgType.ERROR):
                break
    finally:
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump
    return ws


def add_link_routes(app: web.Application) -> None:
    app.router.add_post("/api/connect", handle_connect)
    app.router.add_post("/api/disconnect", handle_disconnect)
    app.router.add_get("/api/telemetry", handle_telemetry_ws)
