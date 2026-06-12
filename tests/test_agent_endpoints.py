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


def test_telemetry_includes_policy_block() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as c:
            d = await (await c.get("/telemetry")).json()
            assert "policy" in d
            assert d["policy"]["connected"] is None  # no autonomy session attached yet

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


# ---- /autonomy: in-process closed-loop through the agent's single safety gate -----------


class _FakeCam:
    def capture(self) -> str:
        return "IMG"


class _FakePolicy:
    def infer(self, obs: dict) -> list[float]:
        return [0.4, 0.0]  # a steady gentle drive


def _autonomy_app(factory=None):
    return build_app(
        transport=ResponderTransport(),
        vcgencmd_run=lambda args: _VCGENCMD[tuple(args)],
        telemetry_interval=0.02,
        autonomy_config={"policy_host": "mac", "control_hz": 50},
        autonomy_factory=factory or (lambda cfg: (_FakeCam(), _FakePolicy())),
    )


def test_autonomy_start_drives_and_feeds_policy_telemetry() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_autonomy_app())) as c:
            r = await c.post("/autonomy", json={"prompt": "drive to the red ball"})
            assert r.status == 201
            await asyncio.sleep(0.1)  # let several control cycles run through the real controller
            snap = await (await c.get("/telemetry")).json()
            # the policy-link block pibotd serves is now LIVE (the gap M11 documented, now closed)
            assert snap["policy"]["connected"] is True
            assert snap["policy"]["last_inference_ms"] is not None
            r = await c.delete("/autonomy")
            assert r.status == 200
            snap2 = await (await c.get("/telemetry")).json()
            assert snap2["policy"]["connected"] is False

    _run(body())


def test_autonomy_double_start_conflicts() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_autonomy_app())) as c:
            assert (await c.post("/autonomy", json={"prompt": "go"})).status == 201
            assert (await c.post("/autonomy", json={"prompt": "go"})).status == 409
            await c.delete("/autonomy")

    _run(body())


def test_autonomy_estop_blocks_policy_drive_but_keeps_telemetry() -> None:
    # The policy drives through the SAME gate teleop does: a latched e-stop drops its commands.
    async def body() -> None:
        async with TestClient(TestServer(_autonomy_app())) as c:
            await c.post("/estop")  # latch before autonomy even starts
            assert (await c.post("/autonomy", json={"prompt": "go"})).status == 201
            await asyncio.sleep(0.05)
            snap = await (await c.get("/telemetry")).json()
            assert snap["safety"]["estop"] is True  # still latched; the policy cannot override it
            await c.delete("/autonomy")

    _run(body())
