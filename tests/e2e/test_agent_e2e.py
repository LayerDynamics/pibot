"""M4 E2E — full client -> agent -> safety -> robot loop, in-process (no hardware).

The headline acceptance: when the operator's command stream goes quiet (a dropped
control connection), the agent's deadman watchdog commands a stop to the robot. This
exercises the real WebSocket client, the real agent, the safety subsystem, and the
firmware-mirror responder as the robot — end to end, no mocks.
"""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestServer

from agent.app import build_app
from pibot.control.client import AgentClient
from pibot.control.teleop import apply_action, key_to_action
from pibot.protocol.codec import decode
from pibot.transport.responder import ResponderTransport


def _run(coro) -> None:
    asyncio.run(coro)


def _vcgencmd(args: list[str]) -> str:
    return {
        ("measure_temp",): "temp=48.0'C",
        ("get_throttled",): "throttled=0x0",
        ("measure_volts", "core"): "volt=0.88V",
    }[tuple(args)]


def test_drive_then_drop_triggers_watchdog_stop() -> None:
    async def body() -> None:
        robot = ResponderTransport()
        app = build_app(transport=robot, vcgencmd_run=_vcgencmd, deadman_ms=80, max_rate_hz=0)
        server = TestServer(app)
        await server.start_server()
        try:
            base = str(server.make_url("")).rstrip("/")
            client = AgentClient(base)
            await client.connect()

            reply = await apply_action(client, key_to_action("w"))  # drive forward
            assert reply is not None and reply["ack"] is True

            # Operator goes quiet (drop). Wait past the deadman window.
            await asyncio.sleep(0.4)
            await client.close()

            stops = [f for f in robot.sent if decode(f, "ascii").name == "stop"]
            assert stops, "watchdog did not stop the robot after the command stream went quiet"
        finally:
            await server.close()

    _run(body())


def test_estop_over_http_latches_robot() -> None:
    async def body() -> None:
        robot = ResponderTransport()
        app = build_app(transport=robot, vcgencmd_run=_vcgencmd, max_rate_hz=0)
        server = TestServer(app)
        await server.start_server()
        try:
            base = str(server.make_url("")).rstrip("/")
            client = AgentClient(base)
            await client.connect()
            await client.estop()
            rejected = await apply_action(client, key_to_action("w"))
            assert rejected is not None and rejected.get("rejected") == "estop"
            # a stop frame reached the robot
            assert any(decode(f, "ascii").name == "stop" for f in robot.sent)
            await client.close()
        finally:
            await server.close()

    _run(body())
