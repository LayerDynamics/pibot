"""App state directory: ~/Library/Application Support/PiBotMissionControl/ (macOS)."""

from __future__ import annotations

import platform
from pathlib import Path


def state_dir() -> Path:
    """Return (and create) the persistent app state directory."""
    if platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "PiBotMissionControl"
    else:
        base = Path.home() / ".pibot-mc"
    base.mkdir(parents=True, exist_ok=True)
    return base
