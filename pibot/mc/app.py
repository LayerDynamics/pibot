"""The Mission Control host aiohttp application: auth middleware + control-plane routes.

The base app wires loopback auth + ``/api/health`` + inventory/config + the robot link
(connect/disconnect/telemetry). Later milestones register video, autonomy, data, metrics,
and ops routes onto this same app. ``McState``/``STATE`` live in :mod:`pibot.mc.state`
(re-exported here) so route modules can import ``STATE`` without an import cycle.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiohttp import web

from pibot.mc.auth import authorize
from pibot.mc.robot_link import RobotLink
from pibot.mc.routes_config import add_config_routes
from pibot.mc.routes_inventory import add_inventory_routes
from pibot.mc.routes_link import add_link_routes
from pibot.mc.state import STATE, McState
from pibot.mc.types import HealthOut

__all__ = ["McState", "STATE", "create_mc_app", "auth_middleware"]

# No public paths: every route is token-gated (unlike pibotd's public /healthz).
PUBLIC_PATHS: frozenset[str] = frozenset()

_Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@web.middleware
async def auth_middleware(request: web.Request, handler: _Handler) -> web.StreamResponse:
    if request.path in PUBLIC_PATHS:
        return await handler(request)
    state = request.app[STATE]
    # Browsers can't set headers on a WebSocket, so accept the token via ?token= as well
    # (the webview's telemetry/video sockets use this); the HTTP header takes precedence.
    auth_header = request.headers.get("Authorization")
    if auth_header is None:
        query_token = request.query.get("token")
        if query_token:
            auth_header = f"Bearer {query_token}"
    reject = authorize(request.remote, auth_header, state.token)
    if reject == 403:
        raise web.HTTPForbidden(text="loopback only")
    if reject == 401:
        raise web.HTTPUnauthorized(text="missing or invalid bearer token")
    return await handler(request)


async def handle_health(request: web.Request) -> web.Response:
    state = request.app[STATE]
    out: HealthOut = {
        "ok": True,
        "version": state.version,
        "connected": state.connected,
        "robot": state.robot,
    }
    return web.json_response(out)


def create_mc_app(*, token: str | None = None, state: McState | None = None) -> web.Application:
    """Build the control-plane app: auth + health + inventory + config + robot link."""
    app = web.Application(middlewares=[auth_middleware])
    st = state or McState(token=token)
    if st.link is None:
        st.link = RobotLink(on_connect=st.on_robot_connect)
    app[STATE] = st
    app.router.add_get("/api/health", handle_health)
    add_inventory_routes(app)
    add_config_routes(app)
    add_link_routes(app)
    return app
