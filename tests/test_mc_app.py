"""T12.1.3 — pibot.mc control-plane sidecar: loopback-only auth + /api/health bind."""

from __future__ import annotations

import asyncio
import contextlib

import aiohttp
from aiohttp.test_utils import TestClient, TestServer

from pibot.mc import __version__
from pibot.mc.app import McState, create_mc_app
from pibot.mc.auth import authorize
from pibot.mc.server import HOST, serve


def _run(coro) -> None:
    asyncio.run(coro)


# ---- authorize() unit (loopback + token gate) ----------------------------


def test_authorize_requires_loopback_and_token() -> None:
    # loopback + valid token -> allow
    assert authorize("127.0.0.1", "Bearer secret", "secret") is None
    assert authorize("::1", "Bearer secret", "secret") is None
    # loopback + bad/missing token -> 401 (other local processes can't get in)
    assert authorize("127.0.0.1", "Bearer wrong", "secret") == 401
    assert authorize("127.0.0.1", None, "secret") == 401
    # non-loopback peer -> 403, even with a valid token
    assert authorize("192.168.1.5", "Bearer secret", "secret") == 403
    assert authorize(None, "Bearer secret", "secret") == 403


# ---- app + auth over a real loopback test client -------------------------


def test_health_returns_status_with_valid_token() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/api/health", headers={"Authorization": "Bearer secret"})
            assert r.status == 200
            data = await r.json()
            assert data == {
                "ok": True,
                "version": __version__,
                "connected": False,
                "robot": None,
            }

    _run(body())


def test_health_rejects_missing_token() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/api/health")
            assert r.status == 401

    _run(body())


def test_query_token_is_accepted_for_browser_sockets() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            # browsers can't set headers on a WebSocket -> token via ?token=
            r = await c.get("/api/health?token=secret")
            assert r.status == 200
            r = await c.get("/api/health?token=wrong")
            assert r.status == 401

    _run(body())


def test_health_reflects_connection_state() -> None:
    async def body() -> None:
        state = McState(token="secret", connected=True, robot="pibot")
        app = create_mc_app(state=state)
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/api/health", headers={"Authorization": "Bearer secret"})
            data = await r.json()
            assert data["connected"] is True
            assert data["robot"] == "pibot"

    _run(body())


# ---- real loopback bind via serve() --------------------------------------


def test_serve_binds_loopback_and_reports_port() -> None:
    assert HOST == "127.0.0.1"

    async def body() -> None:
        bound: dict[str, int] = {}
        ready = asyncio.Event()

        def on_bound(p: int) -> None:
            bound["port"] = p
            ready.set()

        task = asyncio.create_task(serve(token="t", port=0, on_bound=on_bound))
        try:
            await asyncio.wait_for(ready.wait(), timeout=3.0)
            port = bound["port"]
            assert port > 0
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"http://127.0.0.1:{port}/api/health",
                    headers={"Authorization": "Bearer t"},
                ) as r:
                    assert r.status == 200
                    assert (await r.json())["ok"] is True
                async with s.get(f"http://127.0.0.1:{port}/api/health") as r:
                    assert r.status == 401
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    _run(body())
