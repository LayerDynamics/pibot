"""T1.2 — subprocess runner: result propagation and timeout handling."""

from __future__ import annotations

import subprocess

import pytest

from pibot.connection import runner
from pibot.errors import ConnectionError


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_capture_propagates_result(monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        assert kwargs["capture_output"] is True
        return _FakeCompleted(0, "hello\n", "")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run_capture(["ssh", "h", "echo hello"])
    assert result.exit_code == 0
    assert result.stdout == "hello\n"
    assert result.duration >= 0


def test_run_capture_nonzero_exit(monkeypatch) -> None:
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: _FakeCompleted(7, "", "boom"))
    result = runner.run_capture(["ssh", "h", "false"])
    assert result.exit_code == 7
    assert result.stderr == "boom"


def test_run_capture_timeout_raises_connection_error(monkeypatch) -> None:
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    with pytest.raises(ConnectionError):
        runner.run_capture(["ssh", "h", "sleep 100"], timeout=1)


def test_run_interactive_returns_exit_code(monkeypatch) -> None:
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: _FakeCompleted(0))
    assert runner.run_interactive(["ssh", "-t", "h"]) == 0
