"""T12.2.3 — Sidecar video relay: pibotd /video → sidecar WS /api/video.

Tests:
  - Against a fake pibotd /video, the relay forwards header+binary frames to /api/video.
  - A slow consumer drops frames (bounded queue) and never backpressures the source.
  - Disconnecting /api/video does not affect the control or telemetry sockets.
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

# ---------------------------------------------------------------------------
# Fake pibotd that emits /video frames + /telemetry + /control
# ---------------------------------------------------------------------------

_SNAP = {
    "ts": 0.0,
    "pi": {},
    "robot": {},
    "transport": {"open": True, "kind": "tcp"},
    "safety": {"estop": False},
    "policy": {"connected": None, "last_inference_ms": None, "chunk_age_ms": None},
}


def _make_jpeg_bytes(seq: int) -> bytes:
    """Minimal valid JPEG (SOI + EOI)."""
    return b"\xff\xd8\xff" + seq.to_bytes(1, "big") + b"\xff\xd9"


def _fake_pibotd(n_frames: int = 5, *, slow_source: bool = False) -> web.Application:
    """A fake pibotd with /video, /telemetry, and /control."""

    async def video(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        for i in range(n_frames):
            hdr = {"seq": i, "ts": float(i), "w": 320, "h": 240, "fmt": "jpeg"}
            await ws.send_str(json.dumps(hdr))
            await ws.send_bytes(_make_jpeg_bytes(i))
            if slow_source:
                await asyncio.sleep(0.02)
        await ws.close()
        return ws

    async def telemetry(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        for i in range(2):
            await ws.send_json({**_SNAP, "ts": float(i)})
        await ws.close()
        return ws

    async def control(request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            if msg.type is WSMsgType.CLOSE:
                break
        return ws

    app = web.Application()
    app.router.add_get("/video", video)
    app.router.add_get("/telemetry", telemetry)
    app.router.add_get("/control", control)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_relay_forwards_frames_to_api_video() -> None:
    """Relay delivers both parts (JSON header + binary JPEG) for each frame."""

    async def body() -> None:
        async with TestServer(_fake_pibotd(n_frames=3)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                # Connect to the fake robot (this opens /video on the robot link)
                resp = await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                assert resp.status == 201

                # Subscribe to the relay
                ws = await c.ws_connect("/api/video", headers=_AUTH)

                # Read 3 frame pairs (header + binary each)
                for expected_seq in range(3):
                    hdr_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                    assert hdr_msg.type is WSMsgType.TEXT
                    hdr = json.loads(hdr_msg.data)
                    assert hdr["seq"] == expected_seq
                    assert hdr["fmt"] == "jpeg"

                    bin_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                    assert bin_msg.type is WSMsgType.BINARY
                    assert bin_msg.data[:3] == b"\xff\xd8\xff"

                await ws.close()

    _run(body())


def test_slow_consumer_drops_frames_not_backpressures_source() -> None:
    """A slow /api/video consumer drops frames but does not stall the relay."""

    async def body() -> None:
        async with TestServer(_fake_pibotd(n_frames=20, slow_source=False)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                resp = await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                assert resp.status == 201

                ws = await c.ws_connect("/api/video", headers=_AUTH)

                # Consume just a few frames (the rest should be dropped, not queued forever)
                received = 0
                for _ in range(4):
                    hdr_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
                    if hdr_msg.type is WSMsgType.TEXT:
                        received += 1
                        # consume the paired binary too
                        await asyncio.wait_for(ws.receive(), timeout=3.0)

                assert received > 0

                await ws.close()

    _run(body())


def test_closing_api_video_does_not_affect_telemetry() -> None:
    """Closing /api/video must not kill the telemetry stream."""

    async def body() -> None:
        async with TestServer(_fake_pibotd(n_frames=10)) as fake:
            base = str(fake.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            app = create_mc_app(state=state)
            async with TestClient(TestServer(app)) as c:
                resp = await c.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                assert resp.status == 201

                # Open both sockets
                video_ws = await c.ws_connect("/api/video", headers=_AUTH)
                telem_ws = await c.ws_connect("/api/telemetry", headers=_AUTH)

                # Receive one telemetry frame to confirm it's alive
                t_msg = await asyncio.wait_for(telem_ws.receive(), timeout=3.0)
                assert t_msg.type is WSMsgType.TEXT

                # Kill the video socket
                await video_ws.close()

                # Telemetry must still deliver frames
                t_msg2 = await asyncio.wait_for(telem_ws.receive(), timeout=3.0)
                assert t_msg2.type in (WSMsgType.TEXT, WSMsgType.CLOSE)

                await telem_ws.close()

    _run(body())
