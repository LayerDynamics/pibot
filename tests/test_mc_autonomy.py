"""T12.3.1 — Sidecar /api/autonomy routes (start/stop/status → pibotd /autonomy).

Tests:
  - POST /api/autonomy forwards prompt/max_speed/control_hz to pibotd POST /autonomy unchanged.
  - DELETE /api/autonomy delegates to pibotd DELETE /autonomy.
  - GET /api/autonomy returns {running, policy} derived from the pibotd telemetry snapshot.
  - All three endpoints return 503 when no robot is connected.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.robot_link import RobotLink
from pibot.mc.state import McState


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


_AUTH = {"Authorization": "Bearer secret"}

_POLICY_SNAP = {
    "ts": 0.0,
    "pi": {},
    "robot": {},
    "transport": {"open": True, "kind": "tcp"},
    "safety": {"estop": False},
    "policy": {"connected": True, "last_inference_ms": 42.0, "chunk_age_ms": 120.0},
}


def _fake_pibotd_with_autonomy() -> web.Application:
    """Fake pibotd that records /autonomy calls and serves a telemetry snapshot."""
    calls: list[dict] = []

    async def post_autonomy(request: web.Request) -> web.Response:
        data = await request.json()
        calls.append({"method": "POST", "data": data})
        return web.json_response(
            {"autonomy": "started", "prompt": data.get("prompt", "")}, status=201
        )

    async def delete_autonomy(request: web.Request) -> web.Response:
        calls.append({"method": "DELETE"})
        return web.json_response({"autonomy": "stopped"})

    async def telemetry(request: web.Request) -> web.StreamResponse:
        # Handle both WS (telemetry stream) and plain HTTP GET (autonomy_status one-shot).
        if request.headers.get("Upgrade", "").lower() == "websocket":
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            await ws.send_json(_POLICY_SNAP)
            await ws.close()
            return ws
        return web.json_response(_POLICY_SNAP)

    async def video(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.close()
        return ws

    async def control(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.close()
        return ws

    app = web.Application()
    app["calls"] = calls
    app.router.add_post("/autonomy", post_autonomy)
    app.router.add_delete("/autonomy", delete_autonomy)
    app.router.add_get("/telemetry", telemetry)
    app.router.add_get("/video", video)
    app.router.add_get("/control", control)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_post_autonomy_forwards_args_to_pibotd() -> None:
    """POST /api/autonomy passes prompt/max_speed/control_hz to pibotd unchanged."""

    async def body() -> None:
        fake_app = _fake_pibotd_with_autonomy()
        async with TestServer(fake_app) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                r = await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                assert r.status == 201

                r = await c.post(
                    "/api/autonomy",
                    json={"prompt": "navigate to goal", "max_speed": 0.3, "control_hz": 10.0},
                    headers=_AUTH,
                )
                assert r.status == 201
                data = await r.json()
                assert data.get("autonomy") == "started"

                post_call = next((x for x in fake_app["calls"] if x["method"] == "POST"), None)
                assert post_call is not None, "pibotd /autonomy POST was not called"
                assert post_call["data"]["prompt"] == "navigate to goal"
                assert post_call["data"]["max_speed"] == pytest.approx(0.3)
                assert post_call["data"]["control_hz"] == pytest.approx(10.0)

    _run(body())


def test_post_autonomy_without_optional_args() -> None:
    """POST /api/autonomy works with only the required prompt field."""

    async def body() -> None:
        fake_app = _fake_pibotd_with_autonomy()
        async with TestServer(fake_app) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                r = await c.post(
                    "/api/autonomy",
                    json={"prompt": "explore"},
                    headers=_AUTH,
                )
                assert r.status == 201
                post_call = next((x for x in fake_app["calls"] if x["method"] == "POST"), None)
                assert post_call is not None
                assert post_call["data"]["prompt"] == "explore"

    _run(body())


def test_delete_autonomy_stops() -> None:
    """DELETE /api/autonomy delegates to pibotd DELETE /autonomy."""

    async def body() -> None:
        fake_app = _fake_pibotd_with_autonomy()
        async with TestServer(fake_app) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                r = await c.delete("/api/autonomy", headers=_AUTH)
                assert r.status == 200
                data = await r.json()
                assert data.get("autonomy") == "stopped"
                assert any(x["method"] == "DELETE" for x in fake_app["calls"]), (
                    "pibotd DELETE /autonomy was not called"
                )

    _run(body())


def test_get_autonomy_returns_running_and_policy() -> None:
    """GET /api/autonomy returns {running, policy} derived from the telemetry snapshot."""

    async def body() -> None:
        fake_app = _fake_pibotd_with_autonomy()
        async with TestServer(fake_app) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                r = await c.get("/api/autonomy", headers=_AUTH)
                assert r.status == 200
                data = await r.json()
                assert "running" in data
                assert "policy" in data
                assert data["running"] is True
                assert data["policy"]["last_inference_ms"] == pytest.approx(42.0)
                assert data["policy"]["chunk_age_ms"] == pytest.approx(120.0)

    _run(body())


def test_autonomy_endpoints_return_503_when_not_connected() -> None:
    """All /api/autonomy methods return 503 before a robot is connected."""

    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            cases = [
                ("POST", "/api/autonomy", {"prompt": "x"}),
                ("DELETE", "/api/autonomy", None),
                ("GET", "/api/autonomy", None),
            ]
            for method, path, body_json in cases:
                r = await c.request(method, path, headers=_AUTH, json=body_json)
                assert r.status == 503, (
                    f"{method} {path} expected 503 when not connected, got {r.status}"
                )

    _run(body())
