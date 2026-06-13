"""M12.1 E2E — the sidecar control plane against a REAL pibotd (responder transport).

Exercises the full link with no mocks: ``/api/connect`` -> ``RobotLink`` -> ``AgentClient``
-> real ``pibotd`` (``build_app`` + ``ResponderTransport``) -> ``assemble_snapshot``,
relayed back over ``WS /api/telemetry``. The responder is the documented in-memory robot
stand-in, so this runs hermetically in CI (no hardware), like ``test_agent_e2e.py``.
"""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestClient, TestServer

from agent.app import build_app
from pibot.mc.app import create_mc_app
from pibot.mc.robot_link import RobotLink
from pibot.mc.state import McState
from pibot.transport.responder import ResponderTransport

_AUTH = {"Authorization": "Bearer secret"}


def _vcgencmd(args: list[str]) -> str:
    return {
        ("measure_temp",): "temp=48.0'C",
        ("get_throttled",): "throttled=0x0",
        ("measure_volts", "core"): "volt=0.88V",
    }[tuple(args)]


def _run(coro) -> None:
    asyncio.run(coro)


def test_sidecar_relays_real_pibotd_telemetry() -> None:
    async def body() -> None:
        robot = ResponderTransport()
        pibotd = TestServer(build_app(transport=robot, vcgencmd_run=_vcgencmd, max_rate_hz=0))
        await pibotd.start_server()
        try:
            base = str(pibotd.make_url("/")).rstrip("/")
            # Loopback peer is trusted by pibotd's default, so no robot token is needed here.
            state = McState(token="secret", link=RobotLink(resolver=lambda _r: (base, None)))
            sidecar = create_mc_app(state=state)
            async with TestClient(TestServer(sidecar)) as c:
                r = await c.post("/api/connect", json={"robot": "pibot"}, headers=_AUTH)
                assert r.status == 201

                ws = await c.ws_connect("/api/telemetry", headers=_AUTH)
                snap = (await ws.receive()).json()
                await ws.close()

                # Real assemble_snapshot shape, produced by the real agent.
                assert set(snap) >= {"ts", "pi", "robot", "transport", "safety", "policy"}
                assert snap["pi"]["temp_c"] == 48.0
                assert snap["safety"]["estop"] is False
                assert snap["transport"]["open"] is True

                assert (await c.post("/api/disconnect", headers=_AUTH)).status == 200
        finally:
            await pibotd.close()

    _run(body())
