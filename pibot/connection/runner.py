"""Execute argv lists built by :mod:`pibot.connection.sshcmd`.

Two modes: ``run_capture`` for non-interactive commands whose output we collect,
and ``run_interactive`` for commands that take over the terminal (a login shell,
a password prompt). A timeout becomes a :class:`ConnectionError`, never a silent
hang.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass

from pibot.errors import ConnectionError
from pibot.logging import get_logger

_log = get_logger("connection")


@dataclass
class RunResult:
    """Outcome of a captured remote command."""

    exit_code: int
    stdout: str
    stderr: str
    duration: float


def run_capture(
    argv: Sequence[str],
    *,
    timeout: float | None = None,
    input: str | None = None,
) -> RunResult:
    """Run ``argv``, capturing stdout/stderr. Raises ConnectionError on timeout."""
    _log.debug("run_capture: %s", " ".join(argv))
    start = time.monotonic()
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConnectionError(f"command timed out after {timeout}s: {' '.join(argv)}") from exc
    except OSError as exc:
        raise ConnectionError(f"failed to execute {argv[0]!r}: {exc}") from exc
    return RunResult(
        exit_code=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        duration=time.monotonic() - start,
    )


def run_interactive(argv: Sequence[str]) -> int:
    """Run ``argv`` with inherited stdio (interactive). Returns the exit code."""
    _log.debug("run_interactive: %s", " ".join(argv))
    try:
        proc = subprocess.run(list(argv))
    except OSError as exc:
        raise ConnectionError(f"failed to execute {argv[0]!r}: {exc}") from exc
    return proc.returncode
