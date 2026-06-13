"""T12.4.3 — Session recorder + replay."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.sessions import SessionRecorder

_AUTH = {"Authorization": "Bearer secret"}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Unit: SessionRecorder
# ---------------------------------------------------------------------------


def test_session_start_stop_list() -> None:
    r = SessionRecorder()
    sid = r.start(robot="bot")
    assert sid
    assert r.active_id == sid

    sessions = r.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["id"] == sid
    assert sessions[0]["ended"] is None

    rec = r.stop()
    assert rec["id"] == sid
    assert rec["ended"] is not None
    assert r.active_id is None

    sessions = r.list_sessions()
    assert sessions[0]["ended"] is not None


def test_session_add_event_and_replay() -> None:
    r = SessionRecorder()
    sid = r.start(robot="bot")
    r.add_event(kind="control", data={"vx": 0.1, "wz": 0.0})
    r.add_event(kind="estop", data={"reason": "user"})
    r.stop()

    bundle = r.get_session(sid)
    assert bundle is not None
    assert len(bundle["events"]) == 2
    assert bundle["events"][0]["kind"] == "control"
    assert bundle["events"][1]["kind"] == "estop"
    assert bundle["events"][1]["data"]["reason"] == "user"


def test_session_telemetry_window() -> None:
    r = SessionRecorder()
    sid = r.start()
    r.stop()
    bundle = r.get_session(sid)
    assert "telemetry_window" in bundle
    assert bundle["telemetry_window"]["from"] > 0
    assert bundle["telemetry_window"]["to"] >= bundle["telemetry_window"]["from"]


def test_get_session_missing_returns_none() -> None:
    r = SessionRecorder()
    assert r.get_session("nonexistent-uuid") is None


def test_start_while_active_finalizes_previous() -> None:
    r = SessionRecorder()
    sid1 = r.start()
    sid2 = r.start()
    assert sid1 != sid2
    sessions = r.list_sessions()
    assert len(sessions) == 2
    ended = {s["id"]: s["ended"] for s in sessions}
    assert ended[sid1] is not None


def test_add_event_without_active_session_is_noop() -> None:
    r = SessionRecorder()
    r.add_event(kind="control")  # no active session — should not raise


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------


def test_post_session_creates_and_returns_id() -> None:
    async def body() -> None:
        recorder = SessionRecorder()
        app = create_mc_app(token="secret", session_recorder=recorder)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/sessions", headers=_AUTH)
            assert resp.status == 201
            data = await resp.json()
            assert "id" in data
            assert data["started"] is True

    _run(body())


def test_post_and_delete_session_round_trip() -> None:
    async def body() -> None:
        recorder = SessionRecorder()
        app = create_mc_app(token="secret", session_recorder=recorder)
        async with TestClient(TestServer(app)) as client:
            await client.post("/api/sessions", headers=_AUTH)
            resp = await client.delete("/api/sessions", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["ended"] is not None

    _run(body())


def test_get_sessions_lists_all() -> None:
    async def body() -> None:
        recorder = SessionRecorder()
        app = create_mc_app(token="secret", session_recorder=recorder)
        async with TestClient(TestServer(app)) as client:
            await client.post("/api/sessions", headers=_AUTH)
            await client.delete("/api/sessions", headers=_AUTH)
            await client.post("/api/sessions", headers=_AUTH)
            await client.delete("/api/sessions", headers=_AUTH)

            resp = await client.get("/api/sessions", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["sessions"] is not None
            assert len(data["sessions"]) == 2

    _run(body())


def test_get_session_by_id_returns_replay_bundle() -> None:
    async def body() -> None:
        recorder = SessionRecorder()
        app = create_mc_app(token="secret", session_recorder=recorder)
        async with TestClient(TestServer(app)) as client:
            r = await client.post("/api/sessions", headers=_AUTH)
            sid = (await r.json())["id"]

            # Add an event via the events endpoint.
            await client.post(
                "/api/sessions/events",
                json={"kind": "autonomy_start", "data": {"prompt": "explore"}},
                headers=_AUTH,
            )

            await client.delete("/api/sessions", headers=_AUTH)

            r = await client.get(f"/api/sessions/{sid}", headers=_AUTH)
            assert r.status == 200
            bundle = await r.json()
            assert bundle["id"] == sid
            assert len(bundle["events"]) == 1
            assert bundle["events"][0]["kind"] == "autonomy_start"
            assert "telemetry_window" in bundle

    _run(body())


def test_get_session_not_found_returns_404() -> None:
    async def body() -> None:
        recorder = SessionRecorder()
        app = create_mc_app(token="secret", session_recorder=recorder)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/sessions/no-such-id", headers=_AUTH)
            assert resp.status == 404

    _run(body())


def test_delete_session_no_active_returns_409() -> None:
    async def body() -> None:
        recorder = SessionRecorder()
        app = create_mc_app(token="secret", session_recorder=recorder)
        async with TestClient(TestServer(app)) as client:
            resp = await client.delete("/api/sessions", headers=_AUTH)
            assert resp.status == 409

    _run(body())
