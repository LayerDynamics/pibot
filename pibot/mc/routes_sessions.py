"""T12.4.3 — /api/sessions: start/stop/list/get with replay bundle."""

from __future__ import annotations

from aiohttp import web

from pibot.mc.sessions import SessionRecorder
from pibot.mc.state import STATE

SESSION_RECORDER: web.AppKey[SessionRecorder] = web.AppKey("pibot_mc_sessions", SessionRecorder)


async def handle_post_session(request: web.Request) -> web.Response:
    """POST /api/sessions — start a new recording session."""
    recorder = request.app[SESSION_RECORDER]
    state = request.app[STATE]
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    robot = body.get("robot") or state.robot
    sid = recorder.start(robot=robot)
    return web.json_response({"id": sid, "robot": robot, "started": True}, status=201)


async def handle_delete_session(request: web.Request) -> web.Response:
    """DELETE /api/sessions — stop (finalize) the active session."""
    recorder = request.app[SESSION_RECORDER]
    if recorder.active_id is None:
        raise web.HTTPConflict(text="no active session")
    record = recorder.stop()
    return web.json_response(record)


async def handle_get_sessions(request: web.Request) -> web.Response:
    """GET /api/sessions — list all sessions."""
    recorder = request.app[SESSION_RECORDER]
    sessions = recorder.list_sessions()
    return web.json_response({"sessions": sessions})


async def handle_get_session(request: web.Request) -> web.Response:
    """GET /api/sessions/{id} — return the replayable session bundle."""
    recorder = request.app[SESSION_RECORDER]
    sid = request.match_info["id"]
    record = recorder.get_session(sid)
    if record is None:
        raise web.HTTPNotFound(text=f"session {sid} not found")
    return web.json_response(record)


async def handle_post_event(request: web.Request) -> web.Response:
    """POST /api/sessions/events — append an event to the active session."""
    recorder = request.app[SESSION_RECORDER]
    if recorder.active_id is None:
        raise web.HTTPConflict(text="no active session")
    body = await request.json()
    kind = body.get("kind")
    if not kind:
        raise web.HTTPBadRequest(text="kind required")
    recorder.add_event(kind=str(kind), data=body.get("data"))
    return web.json_response({"ok": True})


def add_sessions_routes(
    app: web.Application,
    *,
    session_recorder: SessionRecorder | None = None,
) -> None:
    recorder = session_recorder or SessionRecorder()
    app[SESSION_RECORDER] = recorder
    app.router.add_post("/api/sessions", handle_post_session)
    app.router.add_delete("/api/sessions", handle_delete_session)
    app.router.add_get("/api/sessions", handle_get_sessions)
    app.router.add_get("/api/sessions/{id}", handle_get_session)
    app.router.add_post("/api/sessions/events", handle_post_event)
