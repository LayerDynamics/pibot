"""T12.4.6 — Fine-tune-run tracking + serve-checkpoint."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.finetune import FineTuneRegistry
from pibot.mc.policy_server import PolicyServerManager

_AUTH = {"Authorization": "Bearer secret"}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Unit: FineTuneRegistry
# ---------------------------------------------------------------------------


def test_create_and_list_runs() -> None:
    reg = FineTuneRegistry()
    run = reg.create_run(dataset="/tmp/dataset")
    assert run["status"] == "queued"
    assert run["served"] is False

    runs = reg.list_runs()
    assert len(runs) == 1
    assert runs[0]["id"] == run["id"]


def test_update_run_status_and_checkpoint() -> None:
    reg = FineTuneRegistry()
    run = reg.create_run(dataset="/tmp/ds")
    rid = run["id"]
    updated = reg.update_run(rid, status="running")
    assert updated["status"] == "running"
    updated = reg.update_run(rid, status="done", checkpoint_out="/tmp/ckpt")
    assert updated["status"] == "done"
    assert updated["checkpoint_out"] == "/tmp/ckpt"


def test_mark_served() -> None:
    reg = FineTuneRegistry()
    run = reg.create_run(dataset="/tmp/ds")
    reg.update_run(run["id"], checkpoint_out="/tmp/ckpt")
    served = reg.mark_served(run["id"])
    assert served["served"] is True


def test_get_run_missing_returns_none() -> None:
    reg = FineTuneRegistry()
    assert reg.get_run("no-such-id") is None


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------


def test_list_runs_empty() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret", finetune_registry=FineTuneRegistry())
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/finetune", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["runs"] == []

    _run(body())


def test_post_finetune_creates_run() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret", finetune_registry=FineTuneRegistry())
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/finetune",
                json={"dataset": "/tmp/demo_ds"},
                headers=_AUTH,
            )
            assert resp.status == 201
            run = await resp.json()
            assert run["dataset"] == "/tmp/demo_ds"
            assert run["status"] == "queued"

    _run(body())


def test_post_finetune_requires_dataset() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret", finetune_registry=FineTuneRegistry())
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/finetune", json={}, headers=_AUTH)
            assert resp.status == 400

    _run(body())


def test_get_run_by_id() -> None:
    async def body() -> None:
        reg = FineTuneRegistry()
        run = reg.create_run(dataset="/tmp/ds")
        app = create_mc_app(token="secret", finetune_registry=reg)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(f"/api/finetune/{run['id']}", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["id"] == run["id"]

    _run(body())


def test_get_run_not_found() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret", finetune_registry=FineTuneRegistry())
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/finetune/no-such-id", headers=_AUTH)
            assert resp.status == 404

    _run(body())


def test_patch_run_updates_status() -> None:
    async def body() -> None:
        reg = FineTuneRegistry()
        run = reg.create_run(dataset="/tmp/ds")
        app = create_mc_app(token="secret", finetune_registry=reg)
        async with TestClient(TestServer(app)) as client:
            resp = await client.patch(
                f"/api/finetune/{run['id']}",
                json={"status": "done", "checkpoint_out": "/tmp/ckpt"},
                headers=_AUTH,
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "done"
            assert data["checkpoint_out"] == "/tmp/ckpt"

    _run(body())


def _fake_train_cmd(dataset: str, checkpoint_out: str) -> list[str]:
    """Fake trainer: exits immediately with code 0."""
    return [sys.executable, "-c", "import sys; sys.exit(0)"]


def test_post_finetune_with_train_cmd_launches_and_completes() -> None:
    async def body() -> None:
        reg = FineTuneRegistry()
        app = create_mc_app(
            token="secret",
            finetune_registry=reg,
            train_cmd=_fake_train_cmd,
        )
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/finetune",
                json={"dataset": "/tmp/ds", "checkpoint_out": "/tmp/ckpt"},
                headers=_AUTH,
            )
            assert resp.status == 201
            run = await resp.json()
            rid = run["id"]
            # wait for the background task to complete
            for _ in range(20):
                await asyncio.sleep(0.1)
                r2 = await client.get(f"/api/finetune/{rid}", headers=_AUTH)
                d2 = await r2.json()
                if d2["status"] == "done":
                    break
            else:
                raise AssertionError("trainer task never completed")

    _run(body())


def test_serve_checkpoint_drives_policy_server() -> None:
    """Marking a run served calls PolicyServerManager.start with checkpoint_out."""
    started: list[str] = []

    class _FakePolicyMgr(PolicyServerManager):
        async def start(self, checkpoint: str) -> dict:
            started.append(checkpoint)
            return {"state": "running", "checkpoint": checkpoint}

    async def body() -> None:
        reg = FineTuneRegistry()
        run = reg.create_run(dataset="/tmp/ds")
        reg.update_run(run["id"], status="done", checkpoint_out="/tmp/ckpt")

        policy_mgr = _FakePolicyMgr()
        app = create_mc_app(
            token="secret",
            finetune_registry=reg,
            policy_server=policy_mgr,
        )
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                f"/api/finetune/{run['id']}/serve",
                headers=_AUTH,
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["serving"] is True
            assert data["checkpoint"] == "/tmp/ckpt"

        assert started == ["/tmp/ckpt"]
        assert reg.get_run(run["id"])["served"] is True

    _run(body())


def test_serve_checkpoint_no_checkpoint_out_returns_409() -> None:
    async def body() -> None:
        reg = FineTuneRegistry()
        run = reg.create_run(dataset="/tmp/ds")
        app = create_mc_app(token="secret", finetune_registry=reg)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                f"/api/finetune/{run['id']}/serve",
                headers=_AUTH,
            )
            assert resp.status == 409

    _run(body())
