"""``WS /api/control`` — relay the webview's control frames to ``pibotd WS /control``.

Each incoming ``{cmd, args}`` frame is forwarded to ``pibotd``'s ``/control`` socket and
the reply (ACK / NAK) is returned unchanged.  A :class:`~pibot.mc.cadence.CadenceKeeper`
re-sends the last ``drive`` at :attr:`~pibot.mc.state.McState.teleop_rate_hz` so
``pibotd``'s deadman watchdog stays fed between GUI key-presses.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

import aiohttp
from aiohttp import web

from pibot.mc.cadence import CadenceKeeper
from pibot.mc.state import STATE


async def handle_control_ws(request: web.Request) -> web.StreamResponse:
    """Relay GUI control frames to pibotd; return ACK/NAK unchanged."""
    state = request.app[STATE]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    link = state.link
    robot_url = link.robot_url if link is not None else None
    if robot_url is None:
        await ws.send_json({"error": "not connected"})
        await ws.close()
        return ws

    robot_token = link.robot_token if link is not None else None

    # Build a WS URL for pibotd /control.
    ws_url = robot_url.replace("http://", "ws://").replace("https://", "wss://") + "/control"
    headers = {"Authorization": f"Bearer {robot_token}"} if robot_token else {}

    cadence = CadenceKeeper(rate_hz=state.teleop_rate_hz)

    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            robot_ws = await session.ws_connect(ws_url)
        except Exception as exc:
            await ws.send_json({"error": f"could not reach robot: {exc}"})
            await ws.close()
            return ws

        async def _send_to_robot(cmd: str, args: dict[str, Any]) -> None:
            if not robot_ws.closed:
                await robot_ws.send_json({"cmd": cmd, "args": args})

        cadence.start(_send_to_robot)

        try:
            async for msg in ws:
                if msg.type is web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        cmd = str(data.get("cmd", ""))
                        args = dict(data.get("args", {}))
                    except (ValueError, KeyError):
                        await ws.send_json({"error": "bad frame"})
                        continue

                    cadence.update(cmd, args)

                    if robot_ws.closed:
                        await ws.send_json({"error": "robot disconnected"})
                        break

                    await robot_ws.send_json({"cmd": cmd, "args": args})
                    try:
                        reply_msg = await asyncio.wait_for(robot_ws.receive(), timeout=2.0)
                        if reply_msg.type is aiohttp.WSMsgType.TEXT:
                            reply: dict[str, Any] = json.loads(reply_msg.data)
                            await ws.send_json(reply)
                        else:
                            await ws.send_json({"error": "no reply"})
                    except TimeoutError:
                        await ws.send_json({"error": "robot timeout"})

                elif msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSING, web.WSMsgType.ERROR):
                    break
        finally:
            await cadence.stop()
            with contextlib.suppress(Exception):
                await robot_ws.close()

    return ws


def add_control_routes(app: web.Application) -> None:
    app.router.add_get("/api/control", handle_control_ws)
