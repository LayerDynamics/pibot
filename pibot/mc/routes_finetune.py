"""T12.4.6 — /api/finetune: fine-tune-run tracking + serve-checkpoint.

GET    /api/finetune           — list all runs
POST   /api/finetune           — create + optionally launch a run (fake trainer in CI)
GET    /api/finetune/{id}      — get a single run
PATCH  /api/finetune/{id}      — update status / checkpoint_out
POST   /api/finetune/{id}/serve — serve the run's checkpoint via PolicyServerManager

The ``train_cmd`` factory is injectable: CI passes a fake; production passes the real command.
"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Callable

from aiohttp import web

from pibot.mc.finetune import FineTuneRegistry
from pibot.mc.policy_server import PolicyServerManager
from pibot.mc.routes_policy_server import POLICY_SERVER

FINETUNE_REGISTRY: web.AppKey[FineTuneRegistry] = web.AppKey("pibot_mc_finetune", FineTuneRegistry)

TrainCmd = Callable[[str, str], list[str]]


def _default_train_cmd(dataset: str, checkpoint_out: str) -> list[str]:  # pragma: no cover
    return [
        "python",
        "resources/openpi/scripts/train.py",
        f"--dataset={dataset}",
        f"--output={checkpoint_out}",
    ]


async def handle_list_runs(request: web.Request) -> web.Response:
    reg = request.app[FINETUNE_REGISTRY]
    return web.json_response({"runs": reg.list_runs()})


async def handle_get_run(request: web.Request) -> web.Response:
    reg = request.app[FINETUNE_REGISTRY]
    run = reg.get_run(request.match_info["id"])
    if run is None:
        raise web.HTTPNotFound(text="run not found")
    return web.json_response(run)


async def handle_create_run(request: web.Request) -> web.Response:
    """POST /api/finetune — create a run; if train_cmd is configured, launch it."""
    reg = request.app[FINETUNE_REGISTRY]
    body = await request.json()
    dataset = body.get("dataset")
    checkpoint_out = body.get("checkpoint_out", "")
    if not dataset:
        raise web.HTTPBadRequest(text="dataset required")

    run = reg.create_run(dataset=str(dataset))
    run_id = run["id"]

    train_cmd: TrainCmd | None = request.app.get(_TRAIN_CMD_KEY)
    if train_cmd is not None:
        reg.update_run(run_id, status="running")
        asyncio.create_task(
            _run_training(reg, run_id, train_cmd, str(dataset), str(checkpoint_out))
        )

    return web.json_response(reg.get_run(run_id), status=201)


async def _run_training(
    reg: FineTuneRegistry,
    run_id: str,
    train_cmd: TrainCmd,
    dataset: str,
    checkpoint_out: str,
) -> None:
    cmd = train_cmd(dataset, checkpoint_out)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        await proc.wait()
        status = "done" if proc.returncode == 0 else "error"
        reg.update_run(run_id, status=status, checkpoint_out=checkpoint_out or None)
    except Exception:
        reg.update_run(run_id, status="error")


async def handle_patch_run(request: web.Request) -> web.Response:
    reg = request.app[FINETUNE_REGISTRY]
    run_id = request.match_info["id"]
    if reg.get_run(run_id) is None:
        raise web.HTTPNotFound(text="run not found")
    body = await request.json()
    run = reg.update_run(
        run_id,
        status=body.get("status"),
        checkpoint_out=body.get("checkpoint_out"),
    )
    return web.json_response(run)


async def handle_serve_checkpoint(request: web.Request) -> web.Response:
    """POST /api/finetune/{id}/serve — start PolicyServer with this run's checkpoint."""
    reg = request.app[FINETUNE_REGISTRY]
    run_id = request.match_info["id"]
    run = reg.get_run(run_id)
    if run is None:
        raise web.HTTPNotFound(text="run not found")
    if not run.get("checkpoint_out"):
        raise web.HTTPConflict(text="run has no checkpoint_out")

    policy_mgr: PolicyServerManager | None = request.app.get(POLICY_SERVER)
    if policy_mgr is None:
        raise web.HTTPServiceUnavailable(text="policy server not configured")

    await policy_mgr.start(run["checkpoint_out"])
    reg.mark_served(run_id)
    return web.json_response({"serving": True, "checkpoint": run["checkpoint_out"]})


# AppKey for the injected train_cmd factory.
_TRAIN_CMD_KEY: web.AppKey[TrainCmd] = web.AppKey("pibot_mc_train_cmd", object)  # type: ignore[arg-type]


def add_finetune_routes(
    app: web.Application,
    *,
    registry: FineTuneRegistry | None = None,
    train_cmd: TrainCmd | None = None,
) -> None:
    reg = registry or FineTuneRegistry()
    app[FINETUNE_REGISTRY] = reg
    if train_cmd is not None:
        app[_TRAIN_CMD_KEY] = train_cmd
    app.router.add_get("/api/finetune", handle_list_runs)
    app.router.add_post("/api/finetune", handle_create_run)
    app.router.add_get("/api/finetune/{id}", handle_get_run)
    app.router.add_patch("/api/finetune/{id}", handle_patch_run)
    app.router.add_post("/api/finetune/{id}/serve", handle_serve_checkpoint)
