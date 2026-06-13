"""T12.5.1 — OpsRunner: job lifecycle, guard gating, log streaming, cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from pibot.mc.ops import DESTRUCTIVE, OpsRunner

# ---------------------------------------------------------------------------
# Fake executor
# ---------------------------------------------------------------------------


async def _fake_exec(kind: str, args: dict[str, Any], *, dry_run: bool) -> AsyncIterator[str]:
    if dry_run:
        yield f"[dry-run] would execute {kind}"
    else:
        yield f"[run] executing {kind}"
        yield "step 1/3"
        yield "step 2/3"
        yield "done"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _runner() -> OpsRunner:
    return OpsRunner(exec_fn=_fake_exec)


# ---------------------------------------------------------------------------
# Job creation
# ---------------------------------------------------------------------------


def test_create_job_returns_queued_job() -> None:
    r = _runner()
    job = r.create_job("deploy", {})
    assert job.status == "queued"
    assert job.kind == "deploy"
    assert job.id


def test_create_job_unknown_kind_raises() -> None:
    r = _runner()
    with pytest.raises(ValueError, match="unknown ops kind"):
        r.create_job("nuke", {})


# ---------------------------------------------------------------------------
# Non-destructive (deploy) lifecycle
# ---------------------------------------------------------------------------


def test_deploy_preview_then_confirm_then_run() -> None:
    async def body() -> None:
        r = _runner()
        job = r.create_job("deploy", {"service": "pibotd"})
        await r.preview(job.id)
        assert job.status == "awaiting-confirm"
        assert any("dry-run" in line for line in job.log)

        r.confirm(job.id)
        assert job.confirmed is True

        await r.run(job.id)
        assert job.status == "done"
        assert any("executing deploy" in line for line in job.log)

    _run(body())


# ---------------------------------------------------------------------------
# Destructive kinds require confirmed + guard_passed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(DESTRUCTIVE))
def test_destructive_refuses_run_without_confirmed(kind: str) -> None:
    async def body() -> None:
        r = _runner()
        job = r.create_job(kind, {})
        await r.preview(job.id)
        # guard_passed but NOT confirmed
        r.set_guard(job.id, passed=True)
        with pytest.raises(PermissionError, match="confirmed=True required"):
            await r.run(job.id)
        assert job.status != "done"

    _run(body())


@pytest.mark.parametrize("kind", sorted(DESTRUCTIVE))
def test_destructive_refuses_run_without_guard(kind: str) -> None:
    async def body() -> None:
        r = _runner()
        job = r.create_job(kind, {})
        await r.preview(job.id)
        # confirmed but NOT guard_passed
        r.confirm(job.id, guard_passed=False)
        with pytest.raises(PermissionError, match="guard_passed=True required"):
            await r.run(job.id)
        assert job.status != "done"

    _run(body())


@pytest.mark.parametrize("kind", sorted(DESTRUCTIVE))
def test_destructive_runs_when_both_gates_satisfied(kind: str) -> None:
    async def body() -> None:
        r = _runner()
        job = r.create_job(kind, {})
        await r.preview(job.id)
        r.confirm(job.id, guard_passed=True)
        await r.run(job.id)
        assert job.status == "done"

    _run(body())


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_cancel_running_job() -> None:
    async def body() -> None:
        slow_lines = 0

        async def _slow_exec(kind: str, args: dict, *, dry_run: bool) -> AsyncIterator[str]:
            nonlocal slow_lines
            for i in range(50):
                await asyncio.sleep(0.01)
                slow_lines += 1
                yield f"line {i}"

        r = OpsRunner(exec_fn=_slow_exec)
        job = r.create_job("deploy", {})
        r.confirm(job.id)

        run_task = asyncio.create_task(r.run(job.id))
        await asyncio.sleep(0.05)
        r.cancel(job.id)
        await run_task
        assert job.status == "cancelled"
        assert slow_lines < 50

    _run(body())


# ---------------------------------------------------------------------------
# Log streaming
# ---------------------------------------------------------------------------


def test_stream_log_yields_all_lines() -> None:
    async def body() -> None:
        r = _runner()
        job = r.create_job("deploy", {})
        r.confirm(job.id)

        collected: list[str] = []

        async def _collect() -> None:
            async for line in r.stream_log(job.id):
                collected.append(line)

        collect_task = asyncio.create_task(_collect())
        await r.run(job.id)
        await collect_task

        assert any("executing deploy" in line for line in collected)

    _run(body())


# ---------------------------------------------------------------------------
# list_jobs / get_job
# ---------------------------------------------------------------------------


def test_list_and_get_jobs() -> None:
    r = _runner()
    j1 = r.create_job("deploy", {})
    j2 = r.create_job("flash", {})
    jobs = r.list_jobs()
    assert len(jobs) == 2
    assert r.get_job(j1.id) is j1
    assert r.get_job(j2.id) is j2
    assert r.get_job("no-such-id") is None
