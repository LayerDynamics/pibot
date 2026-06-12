"""T4.1 — pibotd aiohttp app: /healthz (public), /health (gated), bearer-token auth."""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestClient, TestServer

from agent.app import create_app
from agent.auth import is_loopback, load_token, token_ok


def _run(coro) -> None:
    asyncio.run(coro)


# ---- auth unit -----------------------------------------------------------


def test_is_loopback() -> None:
    assert is_loopback("127.0.0.1") is True
    assert is_loopback("::1") is True
    assert is_loopback("192.168.1.5") is False
    assert is_loopback(None) is False
    assert is_loopback("not-an-ip") is False


def test_token_ok() -> None:
    assert token_ok("Bearer secret", "secret") is True
    assert token_ok("Bearer wrong", "secret") is False
    assert token_ok(None, "secret") is False
    assert token_ok("secret", "secret") is False  # missing "Bearer "
    assert token_ok("Bearer secret", None) is False  # no configured token


def test_load_token(tmp_path) -> None:
    p = tmp_path / "agent.token"
    p.write_text("abc123\n", encoding="utf-8")
    assert load_token(p) == "abc123"
    assert load_token(tmp_path / "missing") is None


# ---- app + auth over a real loopback test client -------------------------


def test_healthz_is_public() -> None:
    async def body() -> None:
        app = create_app(token="secret", trust_loopback=False)
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/healthz")
            assert r.status == 200
            assert (await r.text()).strip() == "OK"

    _run(body())


def test_health_allowed_over_trusted_loopback() -> None:
    async def body() -> None:
        app = create_app(token=None, trust_loopback=True, version="9.9.9")
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/health")
            assert r.status == 200
            data = await r.json()
            assert data["version"] == "9.9.9"
            assert "uptime_s" in data

    _run(body())


def test_health_requires_token_when_not_trusted() -> None:
    async def body() -> None:
        app = create_app(token="secret", trust_loopback=False)
        async with TestClient(TestServer(app)) as c:
            assert (await c.get("/health")).status == 401
            ok = await c.get("/health", headers={"Authorization": "Bearer secret"})
            assert ok.status == 200
            bad = await c.get("/health", headers={"Authorization": "Bearer wrong"})
            assert bad.status == 401

    _run(body())


def test_no_configured_token_denies_untrusted() -> None:
    async def body() -> None:
        app = create_app(token=None, trust_loopback=False)
        async with TestClient(TestServer(app)) as c:
            assert (await c.get("/health")).status == 401

    _run(body())


# ---- transport selection (pibotd) ----------------------------------------


def test_build_transport_selects_backend() -> None:
    import pytest

    from agent.pibotd import build_transport
    from pibot.config import Config
    from pibot.errors import UsageError

    assert build_transport(Config(transport="responder")).info["backend"] == "responder"
    assert build_transport(Config(transport="loopback")).info["backend"] == "loopback"
    assert build_transport(Config(transport="tcp", robot_host="1.2.3.4")).info["backend"] == "tcp"
    assert build_transport(Config(transport="serial")).info["backend"] == "serial"
    with pytest.raises(UsageError):
        build_transport(Config(transport="carrier-pigeon"))
