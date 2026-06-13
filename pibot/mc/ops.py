"""T12.5.1 — Ops-job runner: cancellable jobs + streamed log + guards (SPEC-3 §3.7).

Every destructive kind (flash/clone/restore/eeprom) MUST pass:
  1. confirmed=True  (the UI's Radix AlertDialog confirm gate)
  2. guard_passed=True  (pibot/provision/devices.py assert_safe_target gate)

Non-destructive kinds (deploy, firmware-read) only need guard_passed.
"""

from __future__ import annotations

import asyncio
import dataclasses
import uuid
from collections.abc import AsyncIterator
from typing import Any, Protocol

DESTRUCTIVE: frozenset[str] = frozenset({"flash", "clone", "restore", "eeprom"})
VALID_KINDS: frozenset[str] = frozenset(
    {"flash", "clone", "restore", "eeprom", "firmware", "deploy"}
)

_STATUSES = frozenset(
    {"queued", "preview", "awaiting-confirm", "running", "done", "error", "cancelled"}
)


@dataclasses.dataclass
class OpsJob:
    id: str
    kind: str
    args: dict[str, Any]
    dry_run: bool
    confirmed: bool = False
    guard_passed: bool = False
    status: str = "queued"
    progress: float = 0.0
    log: list[str] = dataclasses.field(default_factory=list)
    _cancel_event: asyncio.Event = dataclasses.field(
        default_factory=asyncio.Event, repr=False, compare=False
    )

    def append_log(self, line: str) -> None:
        self.log.append(line)

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def cancelled_requested(self) -> bool:
        return self._cancel_event.is_set()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "args": self.args,
            "dry_run": self.dry_run,
            "confirmed": self.confirmed,
            "guard_passed": self.guard_passed,
            "status": self.status,
            "progress": self.progress,
            "log": list(self.log),
        }


class OpsRunner:
    """Manages the lifecycle of provisioning / ops jobs."""

    def __init__(self, *, exec_fn: _ExecFn | None = None) -> None:
        self._jobs: dict[str, OpsJob] = {}
        # Injected executor: (kind, args, dry_run, log_cb) → async generator of log lines.
        self._exec_fn = exec_fn or _default_exec_fn

    # ------------------------------------------------------------------
    # Job creation
    # ------------------------------------------------------------------

    def create_job(self, kind: str, args: dict[str, Any], *, dry_run: bool = True) -> OpsJob:
        if kind not in VALID_KINDS:
            raise ValueError(f"unknown ops kind: {kind!r}")
        job = OpsJob(id=str(uuid.uuid4()), kind=kind, args=args, dry_run=dry_run)
        self._jobs[job.id] = job
        return job

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    async def preview(self, job_id: str) -> OpsJob:
        """Run the job in dry-run mode to produce a preview log; → preview status."""
        job = self._get(job_id)
        job.status = "preview"
        job.log.clear()
        async for line in self._exec_fn(job.kind, job.args, dry_run=True):
            job.append_log(line)
        if job.kind in DESTRUCTIVE:
            job.status = "awaiting-confirm"
        else:
            job.status = "awaiting-confirm"  # consistent: always need explicit run()
        return job

    def confirm(self, job_id: str, *, guard_passed: bool = False) -> OpsJob:
        """Mark the job as confirmed (+ guard_passed). Destructive ops need both."""
        job = self._get(job_id)
        job.confirmed = True
        if guard_passed:
            job.guard_passed = True
        return job

    def set_guard(self, job_id: str, *, passed: bool) -> OpsJob:
        """Set the wrong-disk guard result on an existing job."""
        job = self._get(job_id)
        job.guard_passed = passed
        return job

    async def run(self, job_id: str) -> OpsJob:
        """Execute the real job after guards are satisfied."""
        job = self._get(job_id)
        self._assert_guards(job)
        job.status = "running"
        job.log.clear()
        try:
            async for line in self._exec_fn(job.kind, job.args, dry_run=False):
                if job.cancelled_requested:
                    job.status = "cancelled"
                    return job
                job.append_log(line)
            job.status = "done"
        except Exception as exc:
            job.append_log(f"error: {exc}")
            job.status = "error"
        return job

    async def stream_log(self, job_id: str) -> AsyncIterator[str]:
        """Async-iterate over log lines as they are appended (polling)."""
        job = self._get(job_id)
        cursor = 0
        while job.status in ("queued", "preview", "running", "awaiting-confirm"):
            while cursor < len(job.log):
                yield job.log[cursor]
                cursor += 1
            await asyncio.sleep(0.05)
        # drain remaining lines
        while cursor < len(job.log):
            yield job.log[cursor]
            cursor += 1

    def cancel(self, job_id: str) -> OpsJob:
        job = self._get(job_id)
        job.cancel()
        if job.status == "running":
            job.status = "cancelled"
        return job

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_job(self, job_id: str) -> OpsJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        return [j.as_dict() for j in self._jobs.values()]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, job_id: str) -> OpsJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"job {job_id!r} not found")
        return job

    @staticmethod
    def _assert_guards(job: OpsJob) -> None:
        if job.kind in DESTRUCTIVE:
            if not job.confirmed:
                raise PermissionError(
                    f"{job.kind} is destructive: confirmed=True required before run()"
                )
            if not job.guard_passed:
                raise PermissionError(
                    f"{job.kind} is destructive: guard_passed=True required before run()"
                )
        else:
            # non-destructive: still need confirmation (but not the disk guard)
            if not job.confirmed:
                raise PermissionError(f"{job.kind}: confirmed=True required before run()")


# ---------------------------------------------------------------------------
# Type alias + default executor (subprocess-based, injectable for tests)
# ---------------------------------------------------------------------------


class _ExecFn(Protocol):
    def __call__(self, kind: str, args: dict[str, Any], *, dry_run: bool) -> AsyncIterator[str]: ...


async def _default_exec_fn(kind: str, args: dict[str, Any], *, dry_run: bool) -> AsyncIterator[str]:
    """Production executor — delegates to the pibot provisioning modules."""
    import asyncio
    import subprocess

    cmd = _build_cmd(kind, args, dry_run=dry_run)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    assert proc.stdout is not None
    async for raw in proc.stdout:
        yield raw.decode(errors="replace").rstrip()
    await proc.wait()


def _build_cmd(kind: str, args: dict[str, Any], *, dry_run: bool) -> list[str]:
    base = ["python", "-m", "pibot.cli", kind]
    if dry_run:
        base.append("--dry-run")
    for k, v in args.items():
        base.extend([f"--{k}", str(v)])
    return base
