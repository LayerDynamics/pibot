"""T2.0 — external flashing-tool resolution and clear install errors."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from pibot.errors import PibotError
from pibot.provision import tools


def test_resolve_uses_path_first(monkeypatch) -> None:
    monkeypatch.setattr(tools, "which", lambda name: "/opt/homebrew/bin/rpiboot")
    assert tools.resolve_tool("rpiboot") == "/opt/homebrew/bin/rpiboot"


def test_resolve_falls_back_to_known_candidate(monkeypatch, tmp_path: Path) -> None:
    exe = tmp_path / "rpiboot"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(tools, "which", lambda name: None)
    monkeypatch.setitem(tools._CANDIDATES, "rpiboot", [str(exe)])
    assert tools.resolve_tool("rpiboot") == str(exe)


def test_resolve_returns_none_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(tools, "which", lambda name: None)
    monkeypatch.setitem(tools._CANDIDATES, "rpiboot", ["/nope/rpiboot"])
    assert tools.resolve_tool("rpiboot") is None


def test_require_tool_raises_with_install_hint(monkeypatch) -> None:
    monkeypatch.setattr(tools, "which", lambda name: None)
    monkeypatch.setitem(tools._CANDIDATES, "rpi-imager", [])
    with pytest.raises(PibotError) as exc:
        tools.require_tool("rpi-imager")
    assert "rpi-imager" in str(exc.value)
    assert "brew" in str(exc.value)  # actionable hint


def test_require_tool_returns_path_when_present(monkeypatch) -> None:
    monkeypatch.setattr(tools, "which", lambda name: "/usr/local/bin/arduino-cli")
    assert tools.require_tool("arduino-cli") == "/usr/local/bin/arduino-cli"


def test_candidate_must_be_executable(monkeypatch, tmp_path: Path) -> None:
    plain = tmp_path / "rpiboot"
    plain.write_text("not executable")
    plain.chmod(plain.stat().st_mode & ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH)
    monkeypatch.setattr(tools, "which", lambda name: None)
    monkeypatch.setitem(tools._CANDIDATES, "rpiboot", [str(plain)])
    assert not os.access(plain, os.X_OK)
    assert tools.resolve_tool("rpiboot") is None
