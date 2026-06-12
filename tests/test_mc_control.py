"""T12.2.4 — Control relay: WS /api/control → pibotd WS /control + cadence keeper.

Tests:
  - drive/stop frames forwarded to pibotd /control; ACK/NAK returned unchanged.
  - The cadence keeper re-sends the last drive at teleop_rate_hz (deadman keep-alive).
  - NAK from pibotd passes through unaltered.
  - Cadence stops on sidecar-side disconnect.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.robot_link import RobotLink
from pibot.mc.state import McState


def _run(coro) -> Any:
    return asyncio.run(coro)


_AUTH = {"Authorization": "Bearer secret"}


def _fake_pibotd(
    *,
    nak_cmd: str | None = None,
    record: list[dict] | None = None,
) -> web.Application:
    """Fake pibotd with /control + /telemetry."""

    async def control(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            if msg.type is WSMsgType.TEXT:
                data = json.loads(msg.data)
                if record is not None:
                    record.append(data)
                cmd = data.get("cmd", "")
                args = data.get("args", {})
                seq = data.get("seq", 0)
                if nak_cmd and cmd == nak_cmd:
                    reply = {"ack": False, "seq": seq, "nak": f"{cmd} clamped"}
                else:
                    reply = {"ack": True, "seq": seq}
                await ws.send_json(reply)
            elif msg.type is WSMsgType.CLOSE:
                break
        return ws

    async def telemetry(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.close()
        return ws

    app = web.Application()
    app.router.add_get("/control", control)
    app.router.add_get("/telemetry", telemetry)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_drive_command_forwarded_and_ack_returned() -> None:
    async def body() -> None:
        received: list[dict] = []
        async with TestServer(_fake_pibotd(record=received)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)

                ws = await c.ws_connect("/api/control", headers=_AUTH)
                await ws.send_json({"cmd": "drive", "args": {"v": 0.3, "w": 0.1}})

                reply_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                assert reply_msg.type is WSMsgType.TEXT
                reply = json.loads(reply_msg.data)
                assert reply["ack"] is True

                # Verify the command arrived at pibotd unchanged.
                assert any(r["cmd"] == "drive" for r in received)
                drive_r = next(r for r in received if r["cmd"] == "drive")
                assert drive_r["args"] == {"v": 0.3, "w": 0.1}

                await ws.close()

    _run(body())


def test_nak_from_pibotd_returned_unchanged() -> None:
    """A pibotd NAK (clamped command) is forwarded to the webview unmodified."""

    async def body() -> None:
        async with TestServer(_fake_pibotd(nak_cmd="drive")) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)

                ws = await c.ws_connect("/api/control", headers=_AUTH)
                await ws.send_json({"cmd": "drive", "args": {"v": 1.0, "w": 0.0}})

                reply_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                reply = json.loads(reply_msg.data)
                # NAK, with the reason from pibotd
                assert reply["ack"] is False
                assert "nak" in reply

                await ws.close()

    _run(body())


def test_cadence_keeper_resends_last_drive() -> None:
    """After a drive command the cadence keeper re-sends it to keep the deadman alive."""

    async def body() -> None:
        received: list[dict] = []
        async with TestServer(_fake_pibotd(record=received)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state, teleop_rate_hz=50)
            async with TestClient(TestServer(app)) as c:
                await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)

                ws = await c.ws_connect("/api/control", headers=_AUTH)
                await ws.send_json({"cmd": "drive", "args": {"v": 0.5, "w": 0.0}})
                # Consume the ACK
                await asyncio.wait_for(ws.receive(), timeout=3.0)

                # Let the cadence keeper tick a few times
                await asyncio.sleep(0.15)

                # pibotd should have received more than one drive (the cadence repeats)
                drive_count = sum(1 for r in received if r.get("cmd") == "drive")
                assert drive_count >= 2, (
                    f"cadence not firing: only {drive_count} drives received"
                )

                await ws.close()

    _run(body())


def test_stop_clears_cadence() -> None:
    """A stop command cancels the repeating cadence."""

    async def body() -> None:
        received: list[dict] = []
        async with TestServer(_fake_pibotd(record=received)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state, teleop_rate_hz=50)
            async with TestClient(TestServer(app)) as c:
                await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)

                ws = await c.ws_connect("/api/control", headers=_AUTH)

                # Start the cadence with a drive.
                await ws.send_json({"cmd": "drive", "args": {"v": 0.5, "w": 0.0}})
                await asyncio.wait_for(ws.receive(), timeout=3.0)

                # Send stop, which should clear the cadence.
                await ws.send_json({"cmd": "stop", "args": {}})
                await asyncio.wait_for(ws.receive(), timeout=3.0)

                # Record count right after stop.
                count_after_stop = len(received)

                # Wait and verify no new cadence frames arrive.
                await asyncio.sleep(0.1)
                count_later = len(received)

                # Should be at most 1 more (a single in-flight tick), not many.
                assert count_later - count_after_stop <= 1, (
                    f"cadence not cleared: {count_later - count_after_stop} extra sends"
                )

                await ws.close()

    _run(body())
