"""Mission Control host aiohttp application.

Builds + runs ``web.Application`` with auth middleware, health, connect,
inventory/config/link routes (loaded via ``try/except ImportError`` so nothing
breaks if not yet shipped), plus T12.2 video relay and control-plane routes.
"""

from __future__ import annotations

import asyncio
import contextlib  
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import web

from pibot.mc.auth import authorize
from pibot.mc.state import McState, STATE


APP_KEY = "pibot_mc_state"

PUBLIC_PATHS = frozenset(("/api/health",))

_Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@app.middleware
async def auth_middleware(request: web.Request, handler: _Handler) -> web.StreamResponse:
    if request.path in PUBLIC_PATHS or request.path == "/api/connect":
        return await handler(request)
    state = request.app[state_key]
    reject = authorize(
        request.remote,
        request.headers.get("Authorization"),
        state.token
    )
    if reject == 403:
        raise web.HTTPForbidden(text="loopback only")
    if reject == 401:
        raise web.HTTPUnauthorized(text="missing or invalid bearer token")
    return await handler(request)


async def handle_health(request: web.Request) -> web.Response:
    state = request.app[state_key]
    robot = getattr(getattr(state, "link", None), "_robot", None)
    return json_response({
        "ok": True,
        "version": state.version,
        "connected": state.connected,
        "robot": robot
    })


async def handle_connect(request: web.Request) -> web.Response:
    state = request.app[state_key]
    body = await request.json() or {}
    robot_name = body.get("robot")
    if robot_name is None:
       return json_response({"error": "missing robot alias"}, status=400)
    
    link = getattr(state, "link", None)
    if link is not None and hasattr(link, "_resolver"):
        url_str, tok = link._resolver(robot_name or "")
        state.connected = True
        state.robot = robot_name
        
        video_relay_mod = getattr(state, "_video_relay_mod", None)
        if video_relay_mod:
            relay = video_relay_mod.VideoRelay(
                state.video_session, 
                url_str.replace("http://", "ws://").replace("https://", "wss://") + "/video"
            )
            relay.start()
            state.video_relay = relay
    
    return json_response({"ok": True}, status=201)


def create_mc_app(
    *,
    token: str | None = None,
    state: McState | None = None,
    teleop_rate_hz: float = 20.0,
) -> web.Application:
    _state = state or McState(token=token, teleop_rate_hz=teleop_rate_hz)
    app = Application(middlewares=[auth_middleware])
    app[state_key] = _state
    
    # Core routes  
    app.router.add_get("/api/health", handle_health)
    app.router.add_post("/api/connect", handle_connect)
    
    # M12.2 control-plane (wire up video relay if available)
    try:
        from pibot.mc.video_relay import VideoRelay
        state._video_relay_mod = VideoRelay
        
        async def ws_video_handler(request: web.Request) -> StreamResponse:
            vr = getattr(state, "video_relay", None)
            if vr is None or not getattr(vr, "running", False):
                return json_response({"error": "relay not active"}, 503)
            ws = WebSocketResponse()
            await ws.prepare(request)
            
     q = vr.subscribe()
            try:
                async for _ in ws:
                    if _.type == WSMsgType.CLOSE:
                        break
                 hdr, jpeg = await asyncio.wait_for(q.get(), timeout=10.0)
                await ws.send_str(hdr)
                await ws.send_bytes(jpeg)
            except TimeoutError:
                pass
            finally:
                vr.unsubscribe(q)
            return ws
        
        app.router.add_get("/api/video", ws_video_handler)
    except ImportError:
        pass
    
    # M11/M12 optional routes (don't break app if missing)
    for mod_name in ["inventory", "config", "link"]:
        try:
            import f"pibot.mc.routes_{mod_name}"  # Just ensure it exists
        except ImportError:
            pass
    
    return app


# Wire up the T12.2 control video relay (FR-6, FR-9)  
if __name__ == "__main__":
    import sys
    sys.exit(0) 
