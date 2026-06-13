"""The Mission Control host aiohttp application: auth middleware + control-plane routes.

The base app wires loopback auth + ``/api/health`` + inventory/config + the robot link
(connect/disconnect/telemetry). M12.2 adds ``/api/video`` (MJPEG relay) and
``/api/control`` (teleop + cadence keep-alive). Later milestones register autonomy,
data, metrics, and ops routes onto this same app. ``McState``/``STATE`` live in
:mod:`pibot.mc.state` (re-exported here) so route modules can import ``STATE`` without
an import cycle.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiohttp import web

from pibot.mc.auth import authorize
from pibot.mc.datasets import EpisodeIndex
from pibot.mc.finetune import FineTuneRegistry
from pibot.mc.metrics import MetricsStore
from pibot.mc.ops import OpsRunner
from pibot.mc.policy_server import PolicyServerManager
from pibot.mc.robot_link import RobotLink
from pibot.mc.routes_autonomy import add_autonomy_routes
from pibot.mc.routes_config import add_config_routes
from pibot.mc.routes_control import add_control_routes
from pibot.mc.routes_episodes import add_episodes_routes
from pibot.mc.routes_finetune import TrainCmd, add_finetune_routes
from pibot.mc.routes_inventory import add_inventory_routes
from pibot.mc.routes_link import add_link_routes
from pibot.mc.routes_metrics import add_metrics_routes
from pibot.mc.routes_ops import add_ops_routes
from pibot.mc.routes_policy_server import add_policy_server_routes
from pibot.mc.routes_record import WriteFn, add_record_routes
from pibot.mc.routes_sessions import add_sessions_routes
from pibot.mc.routes_video import add_video_routes
from pibot.mc.sessions import SessionRecorder
from pibot.mc.state import STATE, McState
from pibot.mc.types import HealthOut

__all__ = ["McState", "STATE", "create_mc_app", "auth_middleware"]

# No public paths: every route is token-gated (unlike pibotd's public /healthz).
PUBLIC_PATHS: frozenset[str] = frozenset()

_Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]

# The webview serves the app from a cross-origin context (`tauri://localhost`,
# `http://tauri.localhost`, or the `http://localhost:1420` dev server), so its fetches to
# this loopback sidecar are cross-origin and must clear CORS. CORS is *not* the security
# boundary — loopback + per-launch token still is; these headers only let the browser read
# the replies it is already authorised to make.
_CORS_METHODS = "GET, POST, PUT, DELETE, OPTIONS"
_CORS_ALLOW_HEADERS = "Authorization, Content-Type"


def _cors_headers(request: web.Request) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": request.headers.get("Origin", "*"),
        "Access-Control-Allow-Methods": _CORS_METHODS,
        "Access-Control-Allow-Headers": _CORS_ALLOW_HEADERS,
        "Access-Control-Max-Age": "600",
        "Vary": "Origin",
    }


@web.middleware
async def auth_middleware(request: web.Request, handler: _Handler) -> web.StreamResponse:
    # CORS preflight: a non-simple request (custom `Authorization` header) makes the browser
    # send an unauthenticated `OPTIONS` first — it carries no token, so it must be answered
    # *before* the auth gate, otherwise every cross-origin call 401s on its preflight.
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=_cors_headers(request))
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
    # Auth failures carry CORS headers too: without them the browser masks the real status
    # as an opaque CORS error, hiding the 401/403 from the operator and from debugging.
    if reject == 403:
        raise web.HTTPForbidden(text="loopback only", headers=_cors_headers(request))
    if reject == 401:
        raise web.HTTPUnauthorized(
            text="missing or invalid bearer token", headers=_cors_headers(request)
        )
    response = await handler(request)
    # Skip already-sent responses (WebSocket upgrades); WS handshakes aren't CORS-gated.
    if not response.prepared:
        response.headers.update(_cors_headers(request))
    return response


async def handle_health(request: web.Request) -> web.Response:
    state = request.app[STATE]
    out: HealthOut = {
        "ok": True,
        "version": state.version,
        "connected": state.connected,
        "robot": state.robot,
    }
    return web.json_response(out)


def create_mc_app(
    *,
    token: str | None = None,
    state: McState | None = None,
    teleop_rate_hz: float = 20.0,
    policy_server: PolicyServerManager | None = None,
    metrics_store: MetricsStore | None = None,
    session_recorder: SessionRecorder | None = None,
    record_write_fn: WriteFn | None = None,
    episode_index: EpisodeIndex | None = None,
    finetune_registry: FineTuneRegistry | None = None,
    train_cmd: TrainCmd | None = None,
    ops_runner: OpsRunner | None = None,
) -> web.Application:
    """Build the control-plane app: auth + health + all route groups."""
    app = web.Application(middlewares=[auth_middleware])
    st = state or McState(token=token, teleop_rate_hz=teleop_rate_hz)
    if st.link is None:
        st.link = RobotLink(on_connect=st.on_robot_connect)
    app[STATE] = st
    app.router.add_get("/api/health", handle_health)
    add_inventory_routes(app)
    add_config_routes(app)
    add_link_routes(app)
    add_video_routes(app)
    add_control_routes(app)
    add_autonomy_routes(app)
    add_policy_server_routes(app, policy_server=policy_server)
    add_metrics_routes(app, metrics_store=metrics_store)
    add_sessions_routes(app, session_recorder=session_recorder)
    add_record_routes(app, write_fn=record_write_fn)
    add_episodes_routes(app, episode_index=episode_index)
    add_finetune_routes(app, registry=finetune_registry, train_cmd=train_cmd)
    add_ops_routes(app, ops_runner=ops_runner)
    return app
