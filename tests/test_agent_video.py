"""T12.2.2 — pibotd WS /video endpoint: auth, JPEG stream, throttle, downscale.

Tests:
  - /video requires bearer (401 without).
  - Emits {seq,ts,w,h,fmt:"jpeg"} JSON header then a binary JPEG per frame.
  - Frames are downscaled so max(w,h) <= video_max_dim.
  - load_config accepts the new int fields (video_fps, video_max_dim) and rejects wrong types.
"""

from __future__ import annotations

import asyncio
import io
import json
from typing import Any

import pytest
from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestClient, TestServer

from agent.app import build_app
from agent.video import CameraBroker
from pibot.transport.responder import ResponderTransport


def _run(coro) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RGBCam:
    """Fake camera returning small PIL Image objects (no numpy required)."""

    def __init__(self, width: int = 480, height: int = 320) -> None:
        from PIL import Image

        self._img = Image.new("RGB", (width, height), color=(100, 150, 200))
        self.capture_count = 0

    def capture(self) -> Any:
        self.capture_count += 1
        return self._img.copy()


def _make_app(video_fps: int = 30, video_max_dim: int = 640) -> web.Application:
    transport = ResponderTransport()
    transport.open()
    return build_app(
        transport=transport,
        token="testtoken",
        trust_loopback=False,
        video_fps=video_fps,
        video_max_dim=video_max_dim,
    )


def _make_app_with_broker(
    cam: _RGBCam,
    *,
    video_fps: int = 30,
    video_max_dim: int = 640,
) -> web.Application:
    transport = ResponderTransport()
    transport.open()
    broker = CameraBroker(cam, fps=100)
    return build_app(
        transport=transport,
        token="testtoken",
        trust_loopback=False,
        broker=broker,
        video_fps=video_fps,
        video_max_dim=video_max_dim,
    )


_AUTH = {"Authorization": "Bearer testtoken"}


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def test_video_ws_requires_bearer() -> None:
    async def body() -> None:
        app = _make_app()
        async with TestClient(TestServer(app)) as c:
            resp = await c.get("/video")
            assert resp.status == 401

    _run(body())


def test_video_ws_allows_valid_bearer() -> None:
    async def body() -> None:
        cam = _RGBCam()
        app = _make_app_with_broker(cam, video_fps=30)
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/video", headers=_AUTH)
            # Should not immediately raise/close with auth error
            assert not ws.closed
            await ws.close()

    _run(body())


# ---------------------------------------------------------------------------
# Frame format: JSON header + binary JPEG
# ---------------------------------------------------------------------------


def test_video_emits_json_header_then_binary_jpeg() -> None:
    async def body() -> None:
        cam = _RGBCam(width=320, height=240)
        app = _make_app_with_broker(cam, video_fps=100, video_max_dim=640)
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/video", headers=_AUTH)

            # First message: JSON header
            hdr_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
            assert hdr_msg.type is WSMsgType.TEXT, f"expected TEXT, got {hdr_msg.type}"
            hdr = json.loads(hdr_msg.data)
            assert "seq" in hdr
            assert "ts" in hdr
            assert "w" in hdr and "h" in hdr
            assert hdr["fmt"] == "jpeg"

            # Second message: binary JPEG payload
            jpeg_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
            assert jpeg_msg.type is WSMsgType.BINARY, f"expected BINARY, got {jpeg_msg.type}"
            payload = jpeg_msg.data
            # JPEG starts with FF D8 FF
            assert payload[:3] == b"\xff\xd8\xff", "payload is not a JPEG"

            # Header dimensions must match what was sent
            from PIL import Image

            img = Image.open(io.BytesIO(payload))
            assert img.size == (hdr["w"], hdr["h"])

            await ws.close()

    _run(body())


def test_video_downscales_large_frame() -> None:
    async def body() -> None:
        cam = _RGBCam(width=1280, height=720)  # bigger than 640
        app = _make_app_with_broker(cam, video_fps=100, video_max_dim=640)
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/video", headers=_AUTH)

            hdr_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
            hdr = json.loads(hdr_msg.data)
            jpeg_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)

            assert max(hdr["w"], hdr["h"]) <= 640, f"frame not downscaled: {hdr['w']}x{hdr['h']}"

            from PIL import Image

            img = Image.open(io.BytesIO(jpeg_msg.data))
            assert max(img.size) <= 640

            await ws.close()

    _run(body())


def test_video_small_frame_not_upscaled() -> None:
    async def body() -> None:
        cam = _RGBCam(width=320, height=240)  # smaller than 640
        app = _make_app_with_broker(cam, video_fps=100, video_max_dim=640)
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/video", headers=_AUTH)

            hdr_msg = await asyncio.wait_for(ws.receive(), timeout=3.0)
            hdr = json.loads(hdr_msg.data)
            await asyncio.wait_for(ws.receive(), timeout=3.0)  # consume binary

            # Small frames must not be upscaled
            assert hdr["w"] == 320 and hdr["h"] == 240

            await ws.close()

    _run(body())


# ---------------------------------------------------------------------------
# Config fields
# ---------------------------------------------------------------------------


def test_config_video_fps_default(isolated_config_dir: str) -> None:
    from pibot.config import load_config

    cfg = load_config()
    assert cfg.video_fps == 10
    assert cfg.video_max_dim == 640


def test_config_video_fields_override(isolated_config_dir: str) -> None:
    from pathlib import Path

    from pibot import tomlio
    from pibot.config import load_config

    path = Path(isolated_config_dir) / "config.toml"
    tomlio.dump({"video_fps": 5, "video_max_dim": 320}, path)
    cfg = load_config()
    assert cfg.video_fps == 5
    assert cfg.video_max_dim == 320


def test_config_video_fps_wrong_type_rejected(isolated_config_dir: str) -> None:
    from pathlib import Path

    from pibot import tomlio
    from pibot.config import load_config
    from pibot.errors import ConfigError

    path = Path(isolated_config_dir) / "config.toml"
    tomlio.dump({"video_fps": "fast"}, path)
    with pytest.raises(ConfigError):
        load_config()
