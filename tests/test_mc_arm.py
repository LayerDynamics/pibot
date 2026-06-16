"""Task #14 — Sidecar /api/arm/telemetry proxy → pibotd GET /arm/telemetry.

Tests:
  - GET /api/arm/telemetry forwards pibotd's arm snapshot unchanged (delegated via AgentClient).
  - It returns 503 when no robot is connected.
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

_ARM_SNAP = {
    "ok": True,
    "enabled": True,
    "num_joints": 3,
    "positions": {"0": 1.0, "1": 2.0, "2": 3.0},
    "ts": 123.0,
    "age_ms": 80.0,
}


def _fake_pibotd_with_arm(
    snapshot: dict[str, Any], received: list[dict[str, Any]] | None = None
) -> web.Application:
    """Fake pibotd serving /arm/telemetry, a /arm/control WS that records the frames it gets
    (acking each), and a /video WS the RobotLink opens on connect."""

    async def arm_telemetry(request: web.Request) -> web.Response:
        return web.json_response(snapshot)

    async def arm_control(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            if msg.type is web.WSMsgType.TEXT:
                frame = msg.json()
                if received is not None:
                    received.append(frame)
                await ws.send_json({"type": "ack"})
            else:
                break
        return ws

    async def video(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/arm/telemetry", arm_telemetry)
    app.router.add_get("/arm/control", arm_control)
    app.router.add_get("/video", video)
    return app


def test_arm_telemetry_proxies_pibotd_snapshot() -> None:
    async def body() -> None:
        fake_app = _fake_pibotd_with_arm(_ARM_SNAP)
        async with TestServer(fake_app) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(token="secret", link=RobotLink(resolver=lambda _: (base, None)))
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                r = await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                assert r.status == 201

                r = await c.get("/api/arm/telemetry", headers=_AUTH)
                assert r.status == 200
                assert await r.json() == _ARM_SNAP

    _run(body())


def test_arm_telemetry_503_when_not_connected() -> None:
    async def body() -> None:
        state = McState(token="secret", link=RobotLink(resolver=lambda _: ("http://unused", None)))
        app = create_mc_app(state=state)
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/api/arm/telemetry", headers=_AUTH)
            assert r.status == 503

    _run(body())


# ---- M-ARM-1 task 1.3: RobotLink delegates arm motion to AgentClient -------


def test_robot_link_arm_motion_delegates_to_client() -> None:
    async def body() -> None:
        received: list[dict[str, Any]] = []
        fake_app = _fake_pibotd_with_arm(_ARM_SNAP, received)
        async with TestServer(fake_app) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            link = RobotLink(resolver=lambda _: (base, None))
            await link.connect("bot")
            try:
                assert (await link.arm_jog(2, 30.0))["type"] == "ack"
                assert (await link.arm_move_joint(1, 45.0, speed=10.0))["type"] == "ack"
                assert (await link.arm_move_joint(0, 5.0))["type"] == "ack"
                assert (await link.arm_home(0))["type"] == "ack"
                assert (await link.arm_estop())["type"] == "ack"
                assert (await link.arm_clear_estop())["type"] == "ack"
                assert (await link.arm_enable(True))["type"] == "ack"
                assert (await link.arm_move_joints({0: 5.0, 1: 6.0}, 2.0))["type"] == "ack"
                assert (await link.arm_grip(40.0))["type"] == "ack"
                assert (await link.arm_tool(True))["type"] == "ack"
                assert (await link.arm_move_cartesian(0.3, 0.0, 0.4, 1.0, rx=0.1))["type"] == "ack"
            finally:
                await link.disconnect()
        cmds = [f["cmd"] for f in received]
        assert cmds == [
            "jvel",
            "jmove",
            "jpos",
            "home",
            "estop",
            "clear_estop",
            "enable",
            "move",
            "grip",
            "tool",
            "move_cartesian",
        ]
        assert received[0] == {"cmd": "jvel", "joint": 2, "dps": 30.0}
        assert received[1]["dps"] == 10.0  # arm_move_joint(speed=) -> jmove
        assert received[7]["targets"] == {"0": 5.0, "1": 6.0}  # JSON stringifies int keys
        assert received[8] == {"cmd": "grip", "deg": 40.0}
        assert received[9] == {"cmd": "tool", "on": True}
        assert received[10] == {
            "cmd": "move_cartesian",
            "x": 0.3,
            "y": 0.0,
            "z": 0.4,
            "rx": 0.1,
            "ry": 0.0,
            "rz": 0.0,
            "seconds": 1.0,
        }

    _run(body())


def test_robot_link_arm_motion_raises_when_not_connected() -> None:
    async def body() -> None:
        link = RobotLink(resolver=lambda _: ("http://unused", None))
        calls = [
            link.arm_jog(0, 1.0),
            link.arm_move_joint(0, 1.0),
            link.arm_move_joints({0: 1.0}, 1.0),
            link.arm_home(0),
            link.arm_estop(),
            link.arm_clear_estop(),
            link.arm_enable(True),
            link.arm_grip(10.0),
            link.arm_tool(True),
            link.arm_move_cartesian(0.3, 0.0, 0.4, 1.0),
        ]
        for coro in calls:
            with pytest.raises(RuntimeError):
                await coro

    _run(body())


# ---- M-ARM-1 task 1.4: MC motion routes proxy to RobotLink -----------------


def test_arm_motion_routes_proxy_to_robot_link() -> None:
    async def body() -> None:
        received: list[dict[str, Any]] = []
        fake_app = _fake_pibotd_with_arm(_ARM_SNAP, received)
        async with TestServer(fake_app) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(token="secret", link=RobotLink(resolver=lambda _: (base, None)))
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                r = await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                assert r.status == 201

                async def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
                    resp = await c.post(path, json=payload, headers=_AUTH)
                    assert resp.status == 200, f"{path} -> {resp.status}"
                    out: dict[str, Any] = await resp.json()
                    return out

                assert (await post("/api/arm/jog", {"joint": 1, "dps": 20.0}))["type"] == "ack"
                await post("/api/arm/move", {"joint": 0, "deg": 30.0})
                await post("/api/arm/move", {"joint": 2, "deg": 15.0, "speed": 5.0})
                await post("/api/arm/move-all", {"targets": {"0": 10.0, "1": 20.0}, "seconds": 2.0})
                await post("/api/arm/home", {"joint": 0})
                await post("/api/arm/estop", {})
                await post("/api/arm/clear_estop", {})
                await post("/api/arm/enable", {"on": False})
                await post("/api/arm/grip", {"deg": 33.0})
                await post("/api/arm/tool", {"on": True})
                await post(
                    "/api/arm/move-cartesian",
                    {"x": 0.25, "y": 0.05, "z": 0.4, "seconds": 1.5, "ry": 0.2},
                )

        cmds = [f["cmd"] for f in received]
        assert cmds == [
            "jvel",
            "jpos",
            "jmove",
            "move",
            "home",
            "estop",
            "clear_estop",
            "enable",
            "grip",
            "tool",
            "move_cartesian",
        ]
        assert received[0] == {"cmd": "jvel", "joint": 1, "dps": 20.0}
        assert received[2]["cmd"] == "jmove" and received[2]["dps"] == 5.0
        assert received[3]["targets"] == {"0": 10.0, "1": 20.0}
        assert received[7] == {"cmd": "enable", "on": False}
        assert received[8] == {"cmd": "grip", "deg": 33.0}
        assert received[9] == {"cmd": "tool", "on": True}
        assert received[10] == {
            "cmd": "move_cartesian",
            "x": 0.25,
            "y": 0.05,
            "z": 0.4,
            "rx": 0.0,
            "ry": 0.2,
            "rz": 0.0,
            "seconds": 1.5,
        }

    _run(body())


def test_arm_motion_routes_503_when_not_connected() -> None:
    async def body() -> None:
        state = McState(token="secret", link=RobotLink(resolver=lambda _: ("http://unused", None)))
        app = create_mc_app(state=state)
        async with TestClient(TestServer(app)) as c:
            for path in (
                "/api/arm/jog",
                "/api/arm/move",
                "/api/arm/move-all",
                "/api/arm/move-cartesian",
                "/api/arm/home",
                "/api/arm/estop",
                "/api/arm/clear_estop",
                "/api/arm/enable",
                "/api/arm/grip",
                "/api/arm/tool",
            ):
                r = await c.post(path, json={}, headers=_AUTH)
                assert r.status == 503, path

    _run(body())


def _fake_pibotd_no_arm_control(snapshot: dict[str, Any]) -> web.Application:
    """Connected pibotd that serves telemetry + /video but NOT /arm/control, so a motion call
    over the link fails upstream (the route should map that to 502, not crash)."""

    async def arm_telemetry(request: web.Request) -> web.Response:
        return web.json_response(snapshot)

    async def video(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/arm/telemetry", arm_telemetry)
    app.router.add_get("/video", video)
    return app


def test_arm_motion_route_502_when_upstream_fails() -> None:
    async def body() -> None:
        async with TestServer(_fake_pibotd_no_arm_control(_ARM_SNAP)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(token="secret", link=RobotLink(resolver=lambda _: (base, None)))
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                assert (
                    await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                ).status == 201
                # /arm/control 404s upstream -> the link call raises -> the route maps it to 502.
                r = await c.post("/api/arm/jog", json={"joint": 0, "dps": 5.0}, headers=_AUTH)
                assert r.status == 502

    _run(body())


def test_arm_motion_route_400_on_bad_body() -> None:
    async def body() -> None:
        received: list[dict[str, Any]] = []
        async with TestServer(_fake_pibotd_with_arm(_ARM_SNAP, received)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(token="secret", link=RobotLink(resolver=lambda _: (base, None)))
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                assert (
                    await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                ).status == 201
                # Missing required fields -> 400 (validated before delegating).
                assert (await c.post("/api/arm/jog", json={}, headers=_AUTH)).status == 400
                # Non-object JSON body -> 400.
                r = await c.post(
                    "/api/arm/move",
                    data="[1,2,3]",
                    headers={**_AUTH, "Content-Type": "application/json"},
                )
                assert r.status == 400
                assert received == []  # nothing reached the robot

    _run(body())
