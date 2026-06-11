"""T4.6 — teleop key mapping (pure) + a real AgentClient<->pibotd round-trip."""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestServer

from agent.app import build_app
from pibot.control.client import AgentClient
from pibot.control.teleop import Action, apply_action, key_to_action, run_teleop
from pibot.transport.responder import ResponderTransport


def _run(coro) -> None:
    asyncio.run(coro)


# ---- pure key mapping ----------------------------------------------------


def test_key_to_action_drive() -> None:
    assert key_to_action("w", speed=0.5) == Action("drive", 0.5, 0.0)
    assert key_to_action("up", speed=0.5) == Action("drive", 0.5, 0.0)
    assert key_to_action("s", speed=0.5) == Action("drive", -0.5, 0.0)
    assert key_to_action("a", turn=1.0) == Action("drive", 0.0, 1.0)
    assert key_to_action("d", turn=1.0) == Action("drive", 0.0, -1.0)


def test_run_teleop_loop_maps_keys_then_quits() -> None:
    sent: list[tuple] = []

    class _FakeClient:
        async def send_command(self, cmd, args=None):
            sent.append((cmd, args))
            return {"ack": True}

        async def estop(self):
            sent.append(("estop", None))
            return {"estop": True}

    keys = iter(["w", " "])  # forward, then e-stop, then idle (None) -> stop, then quit

    def src() -> str | None:
        return next(keys, None)

    # max_ticks bounds the loop; the second-to-last key None maps to stop, then we feed 'q'.
    async def body() -> None:
        # script: w -> drive, space -> estop, None -> stop, then quit via key_source returning 'q'
        seq = iter(["w", " ", "q"])
        await run_teleop(_FakeClient(), lambda: next(seq, None), rate_hz=1000, max_ticks=20)

    asyncio.run(body())
    kinds = [c for c, _ in sent]
    assert kinds[0] == "drive"
    assert ("estop", None) in sent
    assert kinds[-1] == "stop"  # quit sends a final stop


def test_key_to_action_controls() -> None:
    assert key_to_action(" ").kind == "estop"
    assert key_to_action("space").kind == "estop"
    assert key_to_action("x").kind == "stop"
    assert key_to_action("q").kind == "quit"
    # unknown / no key this tick -> stop (so releasing a key stops the robot promptly)
    assert key_to_action("z") == Action("stop")
    assert key_to_action(None) == Action("stop")


# ---- real client <-> agent ----------------------------------------------


async def _serve():
    server = TestServer(
        build_app(
            transport=ResponderTransport(),
            vcgencmd_run=lambda args: (
                "temp=50.0'C" if args == ["measure_temp"] else "throttled=0x0"
            ),
        )
    )
    await server.start_server()
    return server


def test_client_drive_and_estop_roundtrip() -> None:
    async def body() -> None:
        server = await _serve()
        try:
            base = str(server.make_url("")).rstrip("/")
            client = AgentClient(base)
            await client.connect()
            try:
                reply = await apply_action(client, key_to_action("w"))
                assert reply is not None and reply["ack"] is True

                await apply_action(client, key_to_action(" "))  # spacebar -> estop
                rejected = await apply_action(client, key_to_action("w"))
                assert rejected is not None and rejected.get("rejected") == "estop"
            finally:
                await client.close()
        finally:
            await server.close()

    _run(body())


def test_client_reads_telemetry() -> None:
    async def body() -> None:
        server = await _serve()
        try:
            base = str(server.make_url("")).rstrip("/")
            client = AgentClient(base)
            await client.connect()
            try:
                snap = await client.telemetry()
                assert "pi" in snap and "ts" in snap
            finally:
                await client.close()
        finally:
            await server.close()

    _run(body())
