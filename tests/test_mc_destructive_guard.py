"""T12.5.4 — Release-blocking: no path through OpsRunner executes a destructive op
without confirmed=True AND guard_passed=True.

Every destructive kind is fuzz-tested: payloads missing confirm/guard must never
reach a 'done' status.  A planted force/bypass arg must not skip the guard.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from pibot.mc.ops import DESTRUCTIVE, OpsRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fake_exec(kind: str, args: dict, *, dry_run: bool) -> AsyncIterator[str]:
    if dry_run:
        yield f"[dry-run] {kind}"
    else:
        yield f"[run] {kind}"
        yield "done"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _runner() -> OpsRunner:
    return OpsRunner(exec_fn=_fake_exec)


# ---------------------------------------------------------------------------
# Parametrized: every destructive kind
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(DESTRUCTIVE))
def test_destructive_requires_confirmed(kind: str) -> None:
    """confirmed=False always raises, regardless of guard_passed."""

    async def body() -> None:
        r = _runner()
        job = r.create_job(kind, {})
        await r.preview(job.id)
        r.set_guard(job.id, passed=True)  # guard passes, but NOT confirmed
        with pytest.raises(PermissionError):
            await r.run(job.id)
        assert job.status not in ("done", "running"), (
            f"{kind}: reached running/done without confirmed=True"
        )

    _run(body())


@pytest.mark.parametrize("kind", sorted(DESTRUCTIVE))
def test_destructive_requires_guard_passed(kind: str) -> None:
    """guard_passed=False always raises even if confirmed=True."""

    async def body() -> None:
        r = _runner()
        job = r.create_job(kind, {})
        await r.preview(job.id)
        r.confirm(job.id, guard_passed=False)  # confirmed, but NOT guard_passed
        with pytest.raises(PermissionError):
            await r.run(job.id)
        assert job.status not in ("done", "running"), (
            f"{kind}: reached running/done without guard_passed=True"
        )

    _run(body())


@pytest.mark.parametrize("kind", sorted(DESTRUCTIVE))
def test_destructive_runs_only_with_both_gates(kind: str) -> None:
    """Only the combination confirmed=True AND guard_passed=True allows execution."""

    async def body() -> None:
        r = _runner()
        job = r.create_job(kind, {})
        await r.preview(job.id)
        r.confirm(job.id, guard_passed=True)
        await r.run(job.id)
        assert job.status == "done"

    _run(body())


# ---------------------------------------------------------------------------
# Fuzz: payloads that try to skip the guard
# ---------------------------------------------------------------------------

_BYPASS_PAYLOADS: list[dict] = [
    {"force": True},
    {"skip_guard": True},
    {"bypass": "yes"},
    {"confirmed": True},  # snake-case trick in args dict — should not skip
    {"guard_passed": True},  # same
    {"dry_run": False},
    {},
]


@pytest.mark.parametrize("kind", sorted(DESTRUCTIVE))
@pytest.mark.parametrize("bad_args", _BYPASS_PAYLOADS)
def test_no_bypass_via_fuzz_args(kind: str, bad_args: dict) -> None:
    """Planted args cannot bypass the guard gating mechanism."""

    async def body() -> None:
        r = _runner()
        job = r.create_job(kind, bad_args)
        await r.preview(job.id)
        # Never call r.confirm() or r.set_guard() — simulate an attacker
        # who only controls the args dict but not the runner API.
        with pytest.raises(PermissionError):
            await r.run(job.id)
        assert job.status != "done", (
            f"{kind} with args {bad_args!r}: executed without gates satisfied"
        )

    _run(body())


# ---------------------------------------------------------------------------
# Non-destructive (deploy, firmware) still need confirmed but NOT guard_passed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["deploy", "firmware"])
def test_non_destructive_requires_confirmed_not_guard(kind: str) -> None:
    async def body() -> None:
        r = _runner()
        job = r.create_job(kind, {})
        await r.preview(job.id)
        # No guard_passed needed — but confirmed is still required
        with pytest.raises(PermissionError):
            await r.run(job.id)
        r.confirm(job.id, guard_passed=False)
        await r.run(job.id)
        assert job.status == "done"

    _run(body())
