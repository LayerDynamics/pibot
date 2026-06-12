"""Mission Control host aiohttp application.

Tests T12.2.3 + T12.2.4: build ``web.Application`` with auth middleware,
/api/health, /api/connect, /api/video (WS), and /api/control (WS).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from functools import partial

from aiohttp import web

from pibot.mc.auth import authorize
from pibot.mc.cadence import CadenceKeeper
from pibot.mc.state import McState, STATE

__all__ = [
    "McState",
    "STATE",
    "VIDEO_PATHS",
    "create_mc_app",
    "auth_middleware",
]

PUBLIC_PATHS: frozenset[str] = frozenset(("/api/health",))
_LOGGER: logging.Logger = logging.getLogger(__name__)
_Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]

@web.middleware
async def auth_middleware(request: web.Request, handler: _Handler) -> web.StreamResponse:
    if request.path in PUBLIC_PATHS or request.path == "/api/connect":
        return await handler(request)

    state = request.app[STATE]
    auth_header = request.headers.get("Authorization")
    if auth_header is None:
        query_token = request.query.get("token")
        if query_token:
            auth_header = "Bearer " + query_token

    reject = authorize(request.remote, auth_header, state.token)
    if reject == 403:
        raise web.HTTPForbidden(text="loopback only")
    if reject == 401:
        raise web.HTTPUnauthorized(text="missing or invalid bearer token")
    return await handler(request)


async def handle_health(request: web.Request) -> web.Response:
    state = request.app[STATE]
    robot = getattr(state.link, "_robot", None) if state.link else None
    return web.json_response({
        "ok": True,
        "version": state.version,
        "connected": state.connected,
        "robot": robot,
    })


async def handle_connect(request: web.Request) -> web.Response:
    state = request.app[STATE]
    body = await request.json() or {}
    robot_name = body.get("robot")

    link = getattr(state, "link", None)
    if link is not None:
        resolver = getattr(link, "_resolver", None)
        if resolver is not None:
            url_str, _tok = resolver(robot_name or "")  # type: ignore[arg-type]
            state.connected = True
            state.robot = robot_name  # type: ignore[assignment]

            vid_mod = getattr(state, "_video_relay_mod", None)
            if vid_mod is not None:
                from pibot.mc.video_relay import VideoRelay
                ws_url = url_str.replace("http://", "ws://").replace("https://", "wss://") + "/video"
                relay = VideoRelay(state._video_session, ws_url)
                relay.start()
                state.video_relay = relay

        return web.json_response({"ok": True}, status=201)


