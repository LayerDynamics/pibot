"""T4.5 — pibotd endpoints: /telemetry (snapshot + WS push), WS /control, /estop, /config."""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestClient, TestServer

from agent.app import build_app
from pibot.transport.responder import ResponderTransport

_VCGENCMD = {
    ("measure_temp",): "temp=50.0'C\n",
    ("get_throttled",): "throttled=0x0\n",
    ("measure_volts", "core"): "volt=0.88V\n",
}


def _run(coro) -> None:
    asyncio.run(coro)


def _app():
    return build_app(
        transport=ResponderTransport(),
        vcgencmd_run=lambda args: _VCGENCMD[tuple(args)],
        telemetry_interval=0.02,
    )


def test_get_telemetry_snapshot() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as c:
            r = await c.get("/telemetry")
            assert r.status == 200
            d = await r.json()
            assert {"pi", "robot", "transport", "safety", "ts"} <= set(d)
            assert d["pi"]["temp_c"] == 50.0
            assert d["transport"]["backend"] == "responder"

    _run(body())


def test_ws_control_drive_acks() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as c:
            ws = await c.ws_connect("/control")
            await ws.send_json({"cmd": "drive", "args": {"v": 0.5, "w": 0.0}})
            reply = await ws.receive_json()
            assert reply["ack"] is True
            await ws.close()

    _run(body())


def test_post_estop_then_control_rejected() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as c:
            r = await c.post("/estop")
            assert r.status == 200
            assert (await r.json())["estop"] is True
            ws = await c.ws_connect("/control")
            await ws.send_json({"cmd": "drive", "args": {"v": 0.5, "w": 0.0}})
            reply = await ws.receive_json()
            assert reply.get("rejected") == "estop"
            await ws.close()

    _run(body())


def test_ws_telemetry_push() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as c:
            ws = await c.ws_connect("/telemetry")
            snap = await ws.receive_json()
            assert "pi" in snap and "ts" in snap
            await ws.close()

    _run(body())


def test_config_get_and_post() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as c:
            assert (await c.get("/config")).status == 200
            await c.post("/config", json={"label": "rover-1"})
            d = await (await c.get("/config")).json()
            assert d["label"] == "rover-1"

    _run(body())
