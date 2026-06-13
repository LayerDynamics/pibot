"""T12.3.2 — Policy-server manager tests.

Uses a fake server binary (an injected stub Python script) — never the real model in CI.
Tests:
  - POST /api/policy-server starts the server and reports state:"running" + pid + checkpoint.
  - GET /api/policy-server polls current state.
  - DELETE /api/policy-server terminates the server.
  - Serving a different checkpoint = stop + respawn with the new --policy.dir.
  - POST without checkpoint returns 400.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.policy_server import PolicyServerManager

_AUTH = {"Authorization": "Bearer secret"}

# ---------------------------------------------------------------------------
# Fake server binary: binds a TCP port, prints READY, serves health probes.
# ---------------------------------------------------------------------------
_FAKE_SERVER_SCRIPT = """\
import socket, sys, time, signal

def _stop(sig, frame):
    sys.exit(0)

signal.signal(signal.SIGTERM, _stop)

port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1', port))
s.listen(10)
s.settimeout(0.1)
print(f"READY port={s.getsockname()[1]}", flush=True)
while True:
    try:
        conn, _ = s.accept()
        conn.close()
    except socket.timeout:
        pass
    except Exception:
        break
"""


def _write_fake_server(tmp_dir: str) -> Path:
    p = Path(tmp_dir) / "fake_policy_server.py"
    p.write_text(_FAKE_SERVER_SCRIPT)
    return p


def _fake_serve_cmd(script: Path, port: int) -> list[str]:
    """Return argv that starts the fake binary on the given port."""
    return [sys.executable, str(script), str(port)]


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _make_app_with_manager(manager: PolicyServerManager) -> web.Application:
    """Build a minimal MC app with the given policy-server manager injected."""
    return create_mc_app(token="secret", policy_server=manager)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_post_starts_server_running() -> None:
    """POST /api/policy-server spawns the fake binary and reports state:running + pid."""

    async def body() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_fake_server(tmp)
            # Use a free port picked by the OS: bind briefly to reserve one.
            import socket as _sock

            s = _sock.socket()
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
            s.close()

            manager = PolicyServerManager(
                port=free_port,
                serve_cmd=lambda ckpt, port: _fake_serve_cmd(script, port),
            )
            app = _make_app_with_manager(manager)
            async with TestClient(TestServer(app)) as c:
                r = await c.post(
                    "/api/policy-server",
                    json={"checkpoint": "/tmp/ckpt/exp/10000"},
                    headers=_AUTH,
                )
                assert r.status in (200, 201)
                data = await r.json()
                assert data["state"] == "running", f"expected running, got {data['state']}"
                assert data["pid"] is not None
                assert data["checkpoint"] == "/tmp/ckpt/exp/10000"
                assert data["port"] == free_port

                # Cleanup
                await manager.stop()

    _run(body())


def test_get_returns_current_state() -> None:
    """GET /api/policy-server reflects current server state."""

    async def body() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_fake_server(tmp)
            import socket as _sock

            s = _sock.socket()
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
            s.close()

            manager = PolicyServerManager(
                port=free_port,
                serve_cmd=lambda ckpt, port: _fake_serve_cmd(script, port),
            )
            app = _make_app_with_manager(manager)
            async with TestClient(TestServer(app)) as c:
                # Before start: stopped
                r = await c.get("/api/policy-server", headers=_AUTH)
                assert r.status == 200
                data = await r.json()
                assert data["state"] == "stopped"

                # After start: running
                await c.post(
                    "/api/policy-server",
                    json={"checkpoint": "/ckpt"},
                    headers=_AUTH,
                )
                r = await c.get("/api/policy-server", headers=_AUTH)
                data = await r.json()
                assert data["state"] == "running"

                await manager.stop()

    _run(body())


def test_delete_stops_server() -> None:
    """DELETE /api/policy-server terminates the running subprocess."""

    async def body() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_fake_server(tmp)
            import socket as _sock

            s = _sock.socket()
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
            s.close()

            manager = PolicyServerManager(
                port=free_port,
                serve_cmd=lambda ckpt, port: _fake_serve_cmd(script, port),
            )
            app = _make_app_with_manager(manager)
            async with TestClient(TestServer(app)) as c:
                await c.post(
                    "/api/policy-server",
                    json={"checkpoint": "/ckpt"},
                    headers=_AUTH,
                )
                r = await c.get("/api/policy-server", headers=_AUTH)
                assert (await r.json())["state"] == "running"

                r = await c.delete("/api/policy-server", headers=_AUTH)
                assert r.status == 200
                data = await r.json()
                assert data["state"] == "stopped"
                assert data["pid"] is None

    _run(body())


def test_different_checkpoint_triggers_respawn() -> None:
    """POST with a different checkpoint stops the current server and respawns."""

    async def body() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            script = _write_fake_server(tmp)
            import socket as _sock

            s = _sock.socket()
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]
            s.close()

            manager = PolicyServerManager(
                port=free_port,
                serve_cmd=lambda ckpt, port: _fake_serve_cmd(script, port),
            )
            app = _make_app_with_manager(manager)
            async with TestClient(TestServer(app)) as c:
                await c.post(
                    "/api/policy-server",
                    json={"checkpoint": "/ckpt/v1"},
                    headers=_AUTH,
                )
                first_pid = (await (await c.get("/api/policy-server", headers=_AUTH)).json())["pid"]

                # Start with a different checkpoint → respawn
                r = await c.post(
                    "/api/policy-server",
                    json={"checkpoint": "/ckpt/v2"},
                    headers=_AUTH,
                )
                data = await r.json()
                assert data["state"] == "running"
                assert data["checkpoint"] == "/ckpt/v2"
                assert data["pid"] != first_pid, "respawn must create a new process"

                await manager.stop()

    _run(body())


def test_post_without_checkpoint_returns_400() -> None:
    """POST /api/policy-server without a checkpoint field returns 400."""

    async def body() -> None:
        manager = PolicyServerManager()
        app = _make_app_with_manager(manager)
        async with TestClient(TestServer(app)) as c:
            r = await c.post("/api/policy-server", json={}, headers=_AUTH)
            assert r.status == 400

    _run(body())
