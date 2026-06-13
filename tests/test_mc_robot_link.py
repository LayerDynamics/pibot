"""T12.1.5 — RobotLink connect/disconnect + telemetry relay + endpoint-cache seam.

Drives the sidecar's link against a fake ``pibotd`` (a /telemetry WS that pushes frames).
"""

from __future__ import annotations

import asyncio

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.robot_link import RobotLink
from pibot.mc.state import McState

_AUTH = {"Authorization": "Bearer secret"}

_SNAP = {
    "ts": 0.0,
    "pi": {},
    "robot": {},
    "transport": {"open": True, "kind": "tcp"},
    "safety": {"estop": False},
    "policy": {"connected": None, "last_inference_ms": None, "chunk_age_ms": None},
}


def _run(coro) -> None:
    asyncio.run(coro)


def _fake_pibotd(frames: int = 2) -> web.Application:
    async def telemetry(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        for i in range(frames):
            await ws.send_json({**_SNAP, "ts": float(i)})
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/telemetry", telemetry)
    return app


def test_connect_relays_telemetry_and_caches_endpoint() -> None:
    async def body() -> None:
        async with TestServer(_fake_pibotd(frames=2)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            seen: list[tuple[str, str | None]] = []
            state = McState(
                token="secret",
                link=RobotLink(
                    resolver=lambda _robot: (base, "robot-tok"),
                    on_connect=lambda url, tok: seen.append((url, tok)),
                ),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                r = await c.post("/api/connect", json={"robot": "pibot"}, headers=_AUTH)
                assert r.status == 201
                assert (await r.json())["robot"] == "pibot"

                # endpoint-cache seam fired with (url, token) — the e-stop failsafe path
                assert seen == [(base, "robot-tok")]

                h = await (await c.get("/api/health", headers=_AUTH)).json()
                assert h["connected"] is True
                assert h["robot"] == "pibot"

                # telemetry relay forwards the 2 frames pushed by the fake pibotd
                ws = await c.ws_connect("/api/telemetry", headers=_AUTH)
                got: list[float] = []
                async for msg in ws:
                    got.append(msg.json()["ts"])
                    if len(got) >= 2:
                        break
                await ws.close()
                assert got == [0.0, 1.0]

                r = await c.post("/api/disconnect", headers=_AUTH)
                assert r.status == 200
                h = await (await c.get("/api/health", headers=_AUTH)).json()
                assert h["connected"] is False
                assert h["robot"] is None

    _run(body())


def test_telemetry_ws_without_connection_reports_error() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/api/telemetry", headers=_AUTH)
            data = (await ws.receive()).json()
            assert data == {"error": "not connected"}
            await ws.close()

    _run(body())
