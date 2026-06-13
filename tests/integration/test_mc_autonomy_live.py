"""T12.3.6 — Closed-loop autonomy round-trip through the MC sidecar.

Exercises the full path: MC sidecar /api/autonomy → pibotd /autonomy → fake policy drives
through the real safety gate → policy-link telemetry surfaces in MC /api/autonomy.

Uses ``ResponderTransport`` + fake camera + fake policy (no real hardware or ML model).
Runs in the normal pytest suite (no hardware mark needed — fully self-contained).

What is tested here that unit tests cannot prove:
  1. POST /api/autonomy on the MC sidecar correctly forwards the request to a real pibotd
     running the actual AutonomyController with its safety gate.
  2. The policy-link telemetry fields (connected, last_inference_ms, chunk_age_ms) that
     pibotd produces are accessible through MC's GET /api/autonomy.
  3. A stalling policy causes chunk_age_ms to grow beyond the staleness threshold so the
     MC layer can surface the drop-to-stop warning.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from aiohttp.test_utils import TestClient, TestServer

from agent.app import build_app
from pibot.mc.app import create_mc_app
from pibot.mc.robot_link import RobotLink
from pibot.mc.state import McState
from pibot.transport.responder import ResponderTransport

_AUTH = {"Authorization": "Bearer secret"}
_VCGENCMD: dict[tuple[str, ...], str] = {
    ("measure_temp",): "temp=45.0'C",
    ("measure_volts", "core"): "volt=0.8500V",
    ("get_throttled",): "throttled=0x0",
}


class _FakeCam:
    def capture(self) -> str:
        return "IMG"


class _FakePolicy:
    def __init__(self) -> None:
        self.calls = 0

    def infer(self, obs: dict) -> list[float]:
        self.calls += 1
        return [0.2, 0.0]


class _StallingPolicy:
    """Policy that blocks after ``block_after`` calls; mimics a stalled inference server."""

    def __init__(self, *, block_after: int = 1) -> None:
        self._calls = 0
        self._block_after = block_after
        self._gate = threading.Event()
        self._gate.set()  # open initially

    def block(self) -> None:
        self._gate.clear()

    def unblock(self) -> None:
        self._gate.set()

    def infer(self, obs: dict) -> list[float]:
        self._calls += 1
        if self._calls > self._block_after:
            self._gate.wait(timeout=5.0)
        return [0.1, 0.0]


def _pibotd(policy=None) -> Any:
    pol = policy or _FakePolicy()
    return build_app(
        transport=ResponderTransport(),
        vcgencmd_run=lambda args: _VCGENCMD[tuple(args)],
        telemetry_interval=0.02,
        autonomy_config={"policy_host": "mac", "control_hz": 50},
        autonomy_factory=lambda cfg: (_FakeCam(), pol),
    ), pol


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_mc_autonomy_round_trip() -> None:
    """POST /api/autonomy (MC) → pibotd runs cycles → GET /api/autonomy shows connected."""

    async def body() -> None:
        pibotd_app, policy = _pibotd()
        async with TestServer(pibotd_app) as pibotd_srv:
            base = str(pibotd_srv.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            mc_app = create_mc_app(state=state)
            async with TestClient(TestServer(mc_app)) as mc:
                # Connect MC to pibotd.
                r = await mc.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                assert r.status == 201

                # Start autonomy through the MC sidecar.
                r = await mc.post(
                    "/api/autonomy",
                    json={"prompt": "drive to the red ball", "control_hz": 50},
                    headers=_AUTH,
                )
                assert r.status == 201, f"start failed: {await r.text()}"

                # Let several control cycles run.
                await asyncio.sleep(0.15)

                # GET /api/autonomy via MC → policy-link should be connected.
                r = await mc.get("/api/autonomy", headers=_AUTH)
                assert r.status == 200
                data = await r.json()
                assert data["running"] is True, f"expected running=True, got {data}"
                assert data["policy"] is not None
                assert data["policy"]["connected"] is True, (
                    "policy link must be connected after running cycles"
                )
                assert data["policy"]["last_inference_ms"] is not None, (
                    "last_inference_ms must be set after at least one infer call"
                )
                assert policy.calls >= 1, "fake policy must have been called at least once"

                # Stop autonomy.
                r = await mc.delete("/api/autonomy", headers=_AUTH)
                assert r.status == 200

    _run(body())


def test_mc_autonomy_stop_disconnects_policy_link() -> None:
    """DELETE /api/autonomy causes pibotd to report policy disconnected."""

    async def body() -> None:
        pibotd_app, _ = _pibotd()
        async with TestServer(pibotd_app) as pibotd_srv:
            base = str(pibotd_srv.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            mc_app = create_mc_app(state=state)
            async with TestClient(TestServer(mc_app)) as mc:
                await mc.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                await mc.post("/api/autonomy", json={"prompt": "explore"}, headers=_AUTH)
                await asyncio.sleep(0.05)

                # Stop.
                r = await mc.delete("/api/autonomy", headers=_AUTH)
                assert r.status == 200

                # Give pibotd a moment to update its telemetry.
                await asyncio.sleep(0.05)

                r = await mc.get("/api/autonomy", headers=_AUTH)
                data = await r.json()
                assert data["running"] is False
                assert data["policy"]["connected"] is False, (
                    "policy link must be disconnected after stop"
                )

    _run(body())


def test_stalling_policy_raises_chunk_age() -> None:
    """A stalling policy causes chunk_age_ms to exceed the staleness threshold."""
    STALE_MS = 1_000.0

    async def body() -> None:
        staller = _StallingPolicy(block_after=2)
        pibotd_app, _ = _pibotd(policy=staller)
        async with TestServer(pibotd_app) as pibotd_srv:
            base = str(pibotd_srv.make_url("/")).rstrip("/")
            state = McState(
                token="secret",
                link=RobotLink(resolver=lambda _: (base, None)),
            )
            mc_app = create_mc_app(state=state)
            async with TestClient(TestServer(mc_app)) as mc:
                await mc.post("/api/connect", json={"robot": "bot"}, headers=_AUTH)
                await mc.post(
                    "/api/autonomy",
                    json={"prompt": "explore", "control_hz": 50},
                    headers=_AUTH,
                )

                # Let initial cycles run, then block the policy.
                await asyncio.sleep(0.1)
                staller.block()

                # Wait for the stale threshold to be exceeded.
                await asyncio.sleep(STALE_MS / 1000 + 0.3)

                r = await mc.get("/api/autonomy", headers=_AUTH)
                data = await r.json()
                policy = data.get("policy", {})
                chunk_age = policy.get("chunk_age_ms")
                assert chunk_age is not None and chunk_age > STALE_MS, (
                    f"expected chunk_age_ms > {STALE_MS}, got {chunk_age}"
                )

                staller.unblock()
                await mc.delete("/api/autonomy", headers=_AUTH)

    _run(body())
