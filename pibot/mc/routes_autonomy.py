"""/api/autonomy — start, stop, and status for pibotd in-process autonomy (SPEC-3 FR-11).

Delegates directly to AgentClient via RobotLink; no motion logic lives here.
"""

from __future__ import annotations

from aiohttp import web

from pibot.mc.state import STATE


async def handle_post_autonomy(request: web.Request) -> web.Response:
    """POST /api/autonomy — start autonomy with {prompt, max_speed?, control_hz?}."""
    state = request.app[STATE]
    if state.link is None or not state.link.connected:
        raise web.HTTPServiceUnavailable(text="not connected to robot")
    data = await request.json()
    prompt = data.get("prompt")
    if not prompt:
        raise web.HTTPBadRequest(text="prompt required")
    max_speed: float | None = data.get("max_speed")
    control_hz: float | None = data.get("control_hz")
    try:
        result = await state.link.autonomy_start(
            prompt=prompt, max_speed=max_speed, control_hz=control_hz
        )
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"autonomy start failed: {exc}") from exc
    return web.json_response(result, status=201)


async def handle_delete_autonomy(request: web.Request) -> web.Response:
    """DELETE /api/autonomy — stop the running autonomy session."""
    state = request.app[STATE]
    if state.link is None or not state.link.connected:
        raise web.HTTPServiceUnavailable(text="not connected to robot")
    try:
        result = await state.link.autonomy_stop()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"autonomy stop failed: {exc}") from exc
    return web.json_response(result)


async def handle_get_autonomy(request: web.Request) -> web.Response:
    """GET /api/autonomy — return {running, policy} from the telemetry snapshot."""
    state = request.app[STATE]
    if state.link is None or not state.link.connected:
        raise web.HTTPServiceUnavailable(text="not connected to robot")
    try:
        status = await state.link.autonomy_status()
    except Exception as exc:
        raise web.HTTPBadGateway(text=f"autonomy status failed: {exc}") from exc
    return web.json_response(status)


def add_autonomy_routes(app: web.Application) -> None:
    app.router.add_post("/api/autonomy", handle_post_autonomy)
    app.router.add_delete("/api/autonomy", handle_delete_autonomy)
    app.router.add_get("/api/autonomy", handle_get_autonomy)
