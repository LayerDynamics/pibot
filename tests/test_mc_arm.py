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


def _fake_pibotd_with_arm_state(
    snapshot: dict[str, Any],
    *,
    calls: list[dict[str, Any]],
) -> web.Application:
    """Fake pibotd with arm telemetry, motion WS, and pose/program CRUD state."""

    poses: dict[str, dict[str, Any]] = {}
    programs: dict[str, dict[str, Any]] = {}

    async def arm_telemetry(request: web.Request) -> web.Response:
        return web.json_response(snapshot)

    async def arm_control(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            if msg.type is web.WSMsgType.TEXT:
                await ws.send_json({"type": "ack"})
        return ws

    async def pose_list(request: web.Request) -> web.Response:
        return web.json_response({"poses": list(poses.values())})

    async def pose_post(request: web.Request) -> web.Response:
        body = await request.json()
        calls.append({"method": "POST", "path": "/arm/poses", "body": body})
        pose = body.get("pose") or {
            "name": body["name"],
            "joints": {"0": 1.0},
            "created": 1.0,
        }
        poses[pose["name"]] = pose
        return web.json_response(pose, status=201)

    async def pose_get(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if name not in poses:
            raise web.HTTPNotFound()
        return web.json_response(poses[name])

    async def pose_delete(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        poses.pop(name, None)
        calls.append({"method": "DELETE", "path": f"/arm/poses/{name}"})
        return web.json_response({"deleted": name})

    async def program_list(request: web.Request) -> web.Response:
        return web.json_response({"programs": list(programs.values())})

    async def program_post(request: web.Request) -> web.Response:
        body = await request.json()
        calls.append({"method": "POST", "path": "/arm/programs", "body": body})
        programs[body["name"]] = body
        return web.json_response(body, status=201)

    async def program_get(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if name not in programs:
            raise web.HTTPNotFound()
        return web.json_response(programs[name])

    async def program_delete(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        programs.pop(name, None)
        calls.append({"method": "DELETE", "path": f"/arm/programs/{name}"})
        return web.json_response({"deleted": name})

    async def program_run(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        calls.append({"method": "POST", "path": f"/arm/programs/{name}/run"})
        return web.json_response({"running": True, "name": name}, status=202)

    async def program_stop(request: web.Request) -> web.Response:
        calls.append({"method": "POST", "path": "/arm/programs/stop"})
        return web.json_response({"stopped": True})

    async def video(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/arm/telemetry", arm_telemetry)
    app.router.add_get("/arm/control", arm_control)
    app.router.add_get("/arm/poses", pose_list)
    app.router.add_post("/arm/poses", pose_post)
    app.router.add_get("/arm/poses/{name}", pose_get)
    app.router.add_delete("/arm/poses/{name}", pose_delete)
    app.router.add_get("/arm/programs", program_list)
    app.router.add_post("/arm/programs", program_post)
    app.router.add_post("/arm/programs/stop", program_stop)
    app.router.add_get("/arm/programs/{name}", program_get)
    app.router.add_delete("/arm/programs/{name}", program_delete)
    app.router.add_post("/arm/programs/{name}/run", program_run)
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


def test_robot_link_pose_and_program_methods_delegate_to_client() -> None:
    async def body() -> None:
        calls: list[dict[str, Any]] = []
        fake_app = _fake_pibotd_with_arm_state(_ARM_SNAP, calls=calls)
        async with TestServer(fake_app) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            link = RobotLink(resolver=lambda _: (base, None))
            await link.connect("bot")
            try:
                pose = await link.arm_pose_save("ready")
                assert pose["name"] == "ready"
                assert [row["name"] for row in (await link.arm_pose_list())["poses"]] == ["ready"]
                program = {"name": "demo", "steps": [{"kind": "wait", "seconds": 0.1}]}
                assert (await link.arm_program_save(program))["name"] == "demo"
                assert [row["name"] for row in (await link.arm_program_list())["programs"]] == [
                    "demo"
                ]
                assert (await link.arm_program_run("demo"))["running"] is True
                assert (await link.arm_program_stop())["stopped"] is True
                assert (await link.arm_pose_delete("ready"))["deleted"] == "ready"
                assert (await link.arm_program_delete("demo"))["deleted"] == "demo"
            finally:
                await link.disconnect()

        assert calls == [
            {"method": "POST", "path": "/arm/poses", "body": {"name": "ready"}},
            {
                "method": "POST",
                "path": "/arm/programs",
                "body": {"name": "demo", "steps": [{"kind": "wait", "seconds": 0.1}]},
            },
            {"method": "POST", "path": "/arm/programs/demo/run"},
            {"method": "POST", "path": "/arm/programs/stop"},
            {"method": "DELETE", "path": "/arm/poses/ready"},
            {"method": "DELETE", "path": "/arm/programs/demo"},
        ]

    _run(body())


def test_arm_pose_and_program_routes_proxy_to_robot_link() -> None:
    async def body() -> None:
        calls: list[dict[str, Any]] = []
        fake_app = _fake_pibotd_with_arm_state(_ARM_SNAP, calls=calls)
        async with TestServer(fake_app) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(token="secret", link=RobotLink(resolver=lambda _: (base, None)))
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                assert (
                    await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                ).status == 201

                created = await c.post("/api/arm/poses", json={"name": "ready"}, headers=_AUTH)
                assert created.status == 201
                assert (await created.json())["name"] == "ready"
                listed = await (await c.get("/api/arm/poses", headers=_AUTH)).json()
                assert [row["name"] for row in listed["poses"]] == ["ready"]

                prog = {"name": "demo", "steps": [{"kind": "wait", "seconds": 0.1}]}
                assert (await c.post("/api/arm/programs", json=prog, headers=_AUTH)).status == 201
                run = await c.post("/api/arm/programs/demo/run", headers=_AUTH)
                assert run.status == 202
                stop = await c.post("/api/arm/programs/stop", headers=_AUTH)
                assert stop.status == 200
                assert (await c.delete("/api/arm/poses/ready", headers=_AUTH)).status == 200
                assert (await c.delete("/api/arm/programs/demo", headers=_AUTH)).status == 200

        assert calls == [
            {"method": "POST", "path": "/arm/poses", "body": {"name": "ready"}},
            {
                "method": "POST",
                "path": "/arm/programs",
                "body": {"name": "demo", "steps": [{"kind": "wait", "seconds": 0.1}]},
            },
            {"method": "POST", "path": "/arm/programs/demo/run"},
            {"method": "POST", "path": "/arm/programs/stop"},
            {"method": "DELETE", "path": "/arm/poses/ready"},
            {"method": "DELETE", "path": "/arm/programs/demo"},
        ]

    _run(body())
