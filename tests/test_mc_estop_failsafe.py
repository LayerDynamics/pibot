"""T12.2.7 — E-stop failsafe integration: /api/estop relay + deadman behaviour.

Tests:
  - POST /api/estop on the sidecar relays to pibotd /estop (connection-path test).
  - POST /api/estop without a connected robot returns 503.
  - The sidecar's /api/estop is independent of the telemetry/video sockets — calling
    it while those WS links are idle still reaches the robot.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.robot_link import RobotLink
from pibot.mc.state import McState


def _run(coro) -> Any:
    return asyncio.run(coro)


_AUTH = {"Authorization": "Bearer secret"}

_SNAP = {
    "ts": 0.0,
    "pi": {},
    "robot": {},
    "transport": {"open": True, "kind": "tcp"},
    "safety": {"estop": False},
    "policy": {"connected": None, "last_inference_ms": None, "chunk_age_ms": None},
}


def _fake_pibotd(*, record: list[str] | None = None) -> web.Application:
    """Fake pibotd with /estop, /telemetry, /video, /control."""

    async def estop(request: web.Request) -> web.Response:
        if record is not None:
            record.append("estop")
        return web.json_response({"ok": True, "estop": True})

    async def telemetry(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json(_SNAP)
        await ws.close()
        return ws

    async def video(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.close()
        return ws

    async def control(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            if msg.type is WSMsgType.CLOSE:
                break
        return ws

    app = web.Application()
    app.router.add_post("/estop", estop)
    app.router.add_get("/telemetry", telemetry)
    app.router.add_get("/video", video)
    app.router.add_get("/control", control)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_estop_relayed_to_pibotd() -> None:
    """POST /api/estop on the sidecar hits pibotd's /estop endpoint."""

    async def body() -> None:
        called: list[str] = []
        async with TestServer(_fake_pibotd(record=called)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                r = await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                assert r.status == 201

                r = await c.post("/api/estop", headers=_AUTH)
                assert r.status == 200
                data = await r.json()
                assert data.get("estop") is True

                assert "estop" in called, "pibotd /estop was not called"

    _run(body())


def test_estop_without_robot_returns_503() -> None:
    """POST /api/estop before connecting returns 503 Service Unavailable."""

    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            r = await c.post("/api/estop", headers=_AUTH)
            assert r.status == 503

    _run(body())


def test_estop_works_with_telemetry_closed() -> None:
    """E-stop reaches the robot even after the telemetry WS has been closed."""

    async def body() -> None:
        called: list[str] = []
        async with TestServer(_fake_pibotd(record=called)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)

                # Open + close telemetry socket to simulate the sidecar's WS dropping.
                ws = await c.ws_connect("/api/telemetry", headers=_AUTH)
                await ws.close()

                # E-stop must still work.
                r = await c.post("/api/estop", headers=_AUTH)
                assert r.status == 200
                assert "estop" in called

    _run(body())
