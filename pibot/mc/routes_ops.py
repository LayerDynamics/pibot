"""T12.5.2 — /api/ops: job submission + status + log WebSocket.

POST /api/ops/{kind}       — create + preview a job (always dry-run first)
POST /api/ops/{id}/confirm — confirm + set guard, then execute
GET  /api/ops/{id}         — job status / progress
WS   /api/ops/{id}/log     — stream log lines
POST /api/ops/{id}/cancel  — cancel a running job
GET  /api/ops              — list all jobs
"""

from __future__ import annotations

import asyncio
import contextlib

from aiohttp import web

from pibot.mc.ops import VALID_KINDS, OpsRunner

OPS_RUNNER: web.AppKey[OpsRunner] = web.AppKey("pibot_mc_ops_runner", OpsRunner)


async def handle_create_job(request: web.Request) -> web.Response:
    """POST /api/ops/{kind} — create + dry-run preview."""
    runner = request.app[OPS_RUNNER]
    kind = request.match_info["kind"]
    if kind not in VALID_KINDS:
        raise web.HTTPBadRequest(text=f"unknown kind: {kind!r}")
    body = await request.json()
    args = {k: v for k, v in body.items() if k != "dry_run"}
    job = runner.create_job(kind, args, dry_run=True)
    await runner.preview(job.id)
    return web.json_response(job.as_dict(), status=201)


async def handle_confirm_and_run(request: web.Request) -> web.Response:
    """POST /api/ops/{id}/confirm — confirm the job and execute it."""
    runner = request.app[OPS_RUNNER]
    job_id = request.match_info["id"]
    if runner.get_job(job_id) is None:
        raise web.HTTPNotFound(text=f"job {job_id!r} not found")
    body = await request.json()
    guard_passed = bool(body.get("guard_passed", False))
    runner.confirm(job_id, guard_passed=guard_passed)
    try:
        await runner.run(job_id)
    except PermissionError as exc:
        raise web.HTTPForbidden(text=str(exc)) from exc
    job = runner.get_job(job_id)
    assert job is not None
    return web.json_response(job.as_dict())


async def handle_get_job(request: web.Request) -> web.Response:
    """GET /api/ops/{id} — job status."""
    runner = request.app[OPS_RUNNER]
    job = runner.get_job(request.match_info["id"])
    if job is None:
        raise web.HTTPNotFound(text="job not found")
    return web.json_response(job.as_dict())


async def handle_list_jobs(request: web.Request) -> web.Response:
    """GET /api/ops — list all jobs."""
    runner = request.app[OPS_RUNNER]
    return web.json_response({"jobs": runner.list_jobs()})


async def handle_cancel_job(request: web.Request) -> web.Response:
    """POST /api/ops/{id}/cancel — cancel a running job."""
    runner = request.app[OPS_RUNNER]
    job_id = request.match_info["id"]
    if runner.get_job(job_id) is None:
        raise web.HTTPNotFound(text="job not found")
    job = runner.cancel(job_id)
    return web.json_response(job.as_dict())


async def handle_log_ws(request: web.Request) -> web.StreamResponse:
    """WS /api/ops/{id}/log — stream log lines to the webview."""
    runner = request.app[OPS_RUNNER]
    job_id = request.match_info["id"]
    if runner.get_job(job_id) is None:
        raise web.HTTPNotFound(text="job not found")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async def _pump() -> None:
        try:
            async for line in runner.stream_log(job_id):
                if ws.closed:
                    break
                await ws.send_str(line)
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            if not ws.closed:
                with contextlib.suppress(Exception):
                    await ws.close()

    pump = asyncio.create_task(_pump())
    try:
        async for msg in ws:
            if msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSING, web.WSMsgType.ERROR):
                break
    finally:
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump
    return ws


def add_ops_routes(
    app: web.Application,
    *,
    ops_runner: OpsRunner | None = None,
) -> None:
    runner = ops_runner or OpsRunner()
    app[OPS_RUNNER] = runner
    app.router.add_get("/api/ops", handle_list_jobs)
    app.router.add_post("/api/ops/{kind}", handle_create_job)
    app.router.add_get("/api/ops/{id}", handle_get_job)
    app.router.add_post("/api/ops/{id}/confirm", handle_confirm_and_run)
    app.router.add_post("/api/ops/{id}/cancel", handle_cancel_job)
    app.router.add_get("/api/ops/{id}/log", handle_log_ws)
