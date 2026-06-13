"""/api/policy-server — start, stop, and status for the local openpi policy-server subprocess.

The :class:`~pibot.mc.policy_server.PolicyServerManager` lives in the app under
``POLICY_SERVER``; it is created by ``create_mc_app`` so each test/server instance
gets its own manager.
"""

from __future__ import annotations

from aiohttp import web

from pibot.mc.policy_server import PolicyServerManager

POLICY_SERVER: web.AppKey[PolicyServerManager] = web.AppKey(
    "pibot_mc_policy_server", PolicyServerManager
)


async def handle_post_policy_server(request: web.Request) -> web.Response:
    """POST /api/policy-server — start (or restart) with {checkpoint}."""
    manager = request.app[POLICY_SERVER]
    data = await request.json()
    checkpoint = data.get("checkpoint")
    if not checkpoint:
        raise web.HTTPBadRequest(text="checkpoint required")
    try:
        state = await manager.start(str(checkpoint))
    except Exception as exc:
        raise web.HTTPInternalServerError(text=f"start failed: {exc}") from exc
    status_code = 201 if state.state == "running" else 200
    return web.json_response(state.as_dict(), status=status_code)


async def handle_get_policy_server(request: web.Request) -> web.Response:
    """GET /api/policy-server — current server state."""
    manager = request.app[POLICY_SERVER]
    return web.json_response(manager.status().as_dict())


async def handle_delete_policy_server(request: web.Request) -> web.Response:
    """DELETE /api/policy-server — stop the running server."""
    manager = request.app[POLICY_SERVER]
    try:
        state = await manager.stop()
    except Exception as exc:
        raise web.HTTPInternalServerError(text=f"stop failed: {exc}") from exc
    return web.json_response(state.as_dict())


def add_policy_server_routes(
    app: web.Application,
    *,
    policy_server: PolicyServerManager | None = None,
) -> None:
    manager = policy_server or PolicyServerManager()
    app[POLICY_SERVER] = manager
    app.router.add_post("/api/policy-server", handle_post_policy_server)
    app.router.add_get("/api/policy-server", handle_get_policy_server)
    app.router.add_delete("/api/policy-server", handle_delete_policy_server)
