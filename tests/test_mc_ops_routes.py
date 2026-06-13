"""T12.5.2 — /api/ops: job submission, status, confirm+run, cancel, log WS."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.ops import OpsRunner

_AUTH = {"Authorization": "Bearer secret"}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _fake_exec(kind: str, args: dict, *, dry_run: bool) -> AsyncIterator[str]:
    if dry_run:
        yield f"[dry-run] {kind}"
    else:
        yield f"[run] {kind} step 1"
        yield f"[run] {kind} step 2"
        yield "done"


def _app(runner: OpsRunner | None = None) -> Any:
    r = runner or OpsRunner(exec_fn=_fake_exec)
    return create_mc_app(token="secret", ops_runner=r)


# ---------------------------------------------------------------------------
# POST /api/ops/{kind}
# ---------------------------------------------------------------------------


def test_post_ops_creates_and_previews_job() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            resp = await client.post(
                "/api/ops/deploy",
                json={"service": "pibotd"},
                headers=_AUTH,
            )
            assert resp.status == 201
            data = await resp.json()
            assert data["kind"] == "deploy"
            assert data["status"] == "awaiting-confirm"
            assert any("dry-run" in line for line in data["log"])

    _run(body())


def test_post_ops_unknown_kind_returns_400() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            resp = await client.post("/api/ops/nuke", json={}, headers=_AUTH)
            assert resp.status == 400

    _run(body())


# ---------------------------------------------------------------------------
# GET /api/ops/{id}
# ---------------------------------------------------------------------------


def test_get_job_status() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            r = await client.post("/api/ops/deploy", json={}, headers=_AUTH)
            job_id = (await r.json())["id"]

            resp = await client.get(f"/api/ops/{job_id}", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["id"] == job_id

    _run(body())


def test_get_job_not_found_returns_404() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            resp = await client.get("/api/ops/no-such-id", headers=_AUTH)
            assert resp.status == 404

    _run(body())


# ---------------------------------------------------------------------------
# POST /api/ops/{id}/confirm — non-destructive
# ---------------------------------------------------------------------------


def test_confirm_and_run_deploy() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            r = await client.post("/api/ops/deploy", json={}, headers=_AUTH)
            job_id = (await r.json())["id"]

            resp = await client.post(
                f"/api/ops/{job_id}/confirm",
                json={"guard_passed": False},
                headers=_AUTH,
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "done"
            assert any("[run]" in line for line in data["log"])

    _run(body())


# ---------------------------------------------------------------------------
# Destructive guard gating through HTTP
# ---------------------------------------------------------------------------


def test_destructive_without_guard_returns_403() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            r = await client.post("/api/ops/flash", json={}, headers=_AUTH)
            job_id = (await r.json())["id"]

            # confirm=True but guard_passed=False
            resp = await client.post(
                f"/api/ops/{job_id}/confirm",
                json={"guard_passed": False},
                headers=_AUTH,
            )
            assert resp.status == 403

    _run(body())


def test_destructive_with_both_gates_runs() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            r = await client.post("/api/ops/flash", json={}, headers=_AUTH)
            job_id = (await r.json())["id"]

            resp = await client.post(
                f"/api/ops/{job_id}/confirm",
                json={"guard_passed": True},
                headers=_AUTH,
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "done"

    _run(body())


# ---------------------------------------------------------------------------
# GET /api/ops — list
# ---------------------------------------------------------------------------


def test_list_jobs() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            await client.post("/api/ops/deploy", json={}, headers=_AUTH)
            await client.post("/api/ops/deploy", json={}, headers=_AUTH)
            resp = await client.get("/api/ops", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert len(data["jobs"]) == 2

    _run(body())


# ---------------------------------------------------------------------------
# POST /api/ops/{id}/cancel
# ---------------------------------------------------------------------------


def test_cancel_job() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            r = await client.post("/api/ops/deploy", json={}, headers=_AUTH)
            job_id = (await r.json())["id"]

            resp = await client.post(f"/api/ops/{job_id}/cancel", headers=_AUTH)
            assert resp.status == 200
            # job was in awaiting-confirm so cancel returns the current state
            data = await resp.json()
            assert data["id"] == job_id

    _run(body())


# ---------------------------------------------------------------------------
# WS /api/ops/{id}/log
# ---------------------------------------------------------------------------


def test_log_ws_streams_lines() -> None:
    async def body() -> None:
        runner = OpsRunner(exec_fn=_fake_exec)
        app = create_mc_app(token="secret", ops_runner=runner)
        async with TestClient(TestServer(app)) as client:
            r = await client.post("/api/ops/deploy", json={}, headers=_AUTH)
            job_id = (await r.json())["id"]

            # Start a confirm+run in background
            run_task = asyncio.create_task(
                client.post(
                    f"/api/ops/{job_id}/confirm",
                    json={"guard_passed": False},
                    headers=_AUTH,
                )
            )

            collected: list[str] = []
            ws = await client.ws_connect(f"/api/ops/{job_id}/log?token=secret")
            async for msg in ws:
                if msg.type == 1:  # WSMsgType.TEXT
                    collected.append(msg.data)
                else:
                    break
            await ws.close()
            await run_task

            assert any("deploy" in line for line in collected)

    _run(body())
