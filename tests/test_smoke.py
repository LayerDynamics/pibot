"""T0.1 — the package imports and the gate script is present and executable."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_package_imports() -> None:
    import pibot

    assert pibot.__version__


def test_check_script_exists_and_executable() -> None:
    script = REPO_ROOT / "scripts" / "check.sh"
    assert script.is_file()
    assert os.access(script, os.X_OK), "scripts/check.sh must be executable"
