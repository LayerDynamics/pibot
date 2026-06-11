"""Build and upload Arduino firmware via ``arduino-cli``.

Pure argv builders plus thin runners. The reference firmware sketch and its
protocol live under ``firmware/`` (added in milestone M3); this module is the host
side that compiles and flashes it to the connected Arduino.
"""

from __future__ import annotations

from collections.abc import Callable

from pibot.errors import PibotError
from pibot.provision import tools

RunFn = Callable[[list[str]], int]


def compile_argv(sketch: str, fqbn: str, *, binary: str) -> list[str]:
    """Build an ``arduino-cli compile`` argv."""
    return [binary, "compile", "--fqbn", fqbn, sketch]


def upload_argv(sketch: str, fqbn: str, port: str, *, binary: str) -> list[str]:
    """Build an ``arduino-cli upload`` argv."""
    return [binary, "upload", "-p", port, "--fqbn", fqbn, sketch]


def _default_run(argv: list[str]) -> int:  # pragma: no cover - thin subprocess glue
    import subprocess

    return subprocess.run(argv).returncode


def build(sketch: str, *, fqbn: str, binary: str | None = None, run: RunFn | None = None) -> int:
    """Compile ``sketch`` for ``fqbn``."""
    bin_ = binary or tools.require_tool("arduino-cli")
    rc = (run or _default_run)(compile_argv(sketch, fqbn, binary=bin_))
    if rc != 0:
        raise PibotError(f"arduino-cli compile failed (exit {rc})")
    return rc


def flash(
    sketch: str,
    *,
    fqbn: str,
    port: str,
    binary: str | None = None,
    run: RunFn | None = None,
    dry_run: bool = False,
) -> int:
    """Upload ``sketch`` to the Arduino on ``port``."""
    bin_ = binary or tools.require_tool("arduino-cli")
    argv = upload_argv(sketch, fqbn, port, binary=bin_)
    if dry_run:
        from pibot.connection import runner

        return runner.preview(argv, label="firmware flash")
    rc = (run or _default_run)(argv)
    if rc != 0:
        raise PibotError(f"arduino-cli upload failed (exit {rc})")
    return rc
