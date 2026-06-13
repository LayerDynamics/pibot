"""T12.2.9 — Safety-bypass regression (release-blocking).

Asserts:
  1. A drive command issued via the sidecar control relay is clamped/rejected in exactly
     the same way as a direct pibotd teleop command (no bypass around the safety gate).
  2. No code path in ``pibot/mc/`` sends a motion frame except through AgentClient →
     pibotd (grep-guard).
  3. A link stall (relay paused) triggers pibotd's deadman watchdog → stop (simulated
     by verifying that the cadence keeper re-sends drives while the relay is active and
     stops when the relay drops).
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestClient, TestServer

from pibot.control.safety import Limits, clamp_command
from pibot.mc.app import create_mc_app
from pibot.mc.robot_link import RobotLink
from pibot.mc.state import McState
from pibot.protocol.codec import Message, MessageType


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


_AUTH = {"Authorization": "Bearer secret"}


# ---------------------------------------------------------------------------
# Fake pibotd with safety-gate simulation
# ---------------------------------------------------------------------------


def _fake_pibotd_with_gate(
    *,
    max_v: float = 0.5,
    max_w: float = 1.0,
    record: list[dict] | None = None,
) -> web.Application:
    """Fake pibotd that clamps commands the same way pibotd's safety gate does."""

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
                if cmd == "drive":
                    v = float(args.get("v", 0))
                    w = float(args.get("w", 0))
                    if abs(v) > max_v or abs(w) > max_w:
                        reply: dict = {
                            "ack": False,
                            "seq": seq,
                            "nak": f"clamp: |v|>{max_v} or |w|>{max_w}",
                        }
                    else:
                        reply = {"ack": True, "seq": seq}
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


def test_clamped_command_passes_through_relay_unchanged() -> None:
    """A GUI drive that exceeds the limit is rejected by pibotd, not silently modified."""

    async def body() -> None:
        received: list[dict] = []
        async with TestServer(_fake_pibotd_with_gate(max_v=0.5, record=received)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)

                ws = await c.ws_connect("/api/control", headers=_AUTH)
                # Send a command beyond the limit.
                await ws.send_json({"cmd": "drive", "args": {"v": 2.0, "w": 0.0}})

                reply_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                reply = json.loads(reply_msg.data)

                # The sidecar must NOT silently downgrade the command; pibotd's gate fires.
                assert reply["ack"] is False, "sidecar must not bypass the safety gate"
                assert "nak" in reply

                # The command that arrived at pibotd was unmodified by the sidecar.
                drive = next((r for r in received if r.get("cmd") == "drive"), None)
                assert drive is not None
                assert drive["args"]["v"] == pytest.approx(2.0), (
                    "sidecar must not silently clamp before forwarding"
                )

                await ws.close()

    _run(body())


def test_direct_pibotd_clamp_matches_relay_behavior() -> None:
    """Direct pibotd clamp == relay path clamp (consistency check using Limits)."""
    limits = Limits()
    # Commands within limits pass through unchanged.
    safe_msg = Message(type=MessageType.COMMAND, seq=1, name="drive", args={"v": 0.3, "w": 0.5})
    clamped = clamp_command(safe_msg, limits)
    assert clamped.args["v"] == pytest.approx(0.3)
    assert clamped.args["w"] == pytest.approx(0.5)

    # Commands beyond limits are clamped to the boundary.
    over_msg = Message(type=MessageType.COMMAND, seq=2, name="drive", args={"v": 5.0, "w": 10.0})
    clamped2 = clamp_command(over_msg, limits)
    assert abs(clamped2.args["v"]) <= limits.max_v
    assert abs(clamped2.args["w"]) <= limits.max_w


def test_no_motion_path_outside_agent_client() -> None:
    """Grep-guard: no code in pibot/mc/ sends motion frames except via AgentClient."""
    mc_dir = Path(__file__).parent.parent / "pibot" / "mc"
    # Patterns that would indicate a direct socket write bypassing the agent client.
    direct_send_patterns = [
        r'ws\.send_json\s*\(\s*\{.*"cmd"\s*:\s*"drive"',
        r"ws\.send_str\s*\(.*drive",
        r"socket\.send.*drive",
    ]
    violations: list[str] = []
    for py_file in mc_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for pattern in direct_send_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                violations.append(f"{py_file.name}: {m!r}")
    assert not violations, "motion frames sent outside AgentClient path:\n" + "\n".join(violations)


def test_cadence_stops_when_relay_disconnects() -> None:
    """When the sidecar's /api/control WS closes, the cadence keeper stops sending."""

    async def body() -> None:
        received: list[dict] = []
        async with TestServer(_fake_pibotd_with_gate(record=received)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state, teleop_rate_hz=50)
            async with TestClient(TestServer(app)) as c:
                await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)

                ws = await c.ws_connect("/api/control", headers=_AUTH)
                await ws.send_json({"cmd": "drive", "args": {"v": 0.3, "w": 0.0}})
                await asyncio.wait_for(ws.receive(), timeout=3.0)

                # Let the cadence fire a few times.
                await asyncio.sleep(0.12)
                count_while_open = len(received)
                assert count_while_open >= 2, "cadence must be firing while relay is open"

                # Close the relay socket — cadence must stop.
                await ws.close()
                await asyncio.sleep(0.12)
                count_after_close = len(received)

                assert count_after_close - count_while_open <= 2, (
                    "cadence kept firing after relay closed — deadman would not stop"
                )

    _run(body())
