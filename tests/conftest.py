"""Shared pytest fixtures for the PiBot Control Suite test-suite."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path, monkeypatch) -> Iterator[str]:
    """Point pibot's config/inventory at a throwaway dir for every test.

    Guarantees no test ever reads or writes the developer's real
    ``~/.config/pibot`` state.
    """
    cfg_dir = tmp_path / "pibot-config"
    cfg_dir.mkdir()
    monkeypatch.setenv("PIBOT_CONFIG_DIR", str(cfg_dir))
    yield str(cfg_dir)
    os.environ.pop("PIBOT_CONFIG_DIR", None)
