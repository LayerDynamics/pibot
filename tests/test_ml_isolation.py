"""T7.1 — the optional ML stack (openpi-client, numpy<2.0, opencv) must stay isolated.

The VLA client introduces a `numpy>=1.22.4,<2.0` pin (from openpi-client). If the core
CLI/agent imported it, that pin could destabilize the whole stdlib-light suite (SPEC-2
FR-8, R-4). These tests assert (a) the `ml` extra is declared with the pin, and (b)
importing the core never pulls the ML deps in — a regression guard as `pibot/ml/*` grows.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_ML_NAMES = ("numpy", "openpi_client", "cv2", "openpi")


def _ml_extra() -> list[str]:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["optional-dependencies"]["ml"]


def test_ml_extra_declared_with_numpy_pin() -> None:
    ml = _ml_extra()
    assert any("openpi-client" in d or "openpi_client" in d for d in ml), (
        "ml extra needs openpi-client"
    )
    assert any("numpy" in d and "<2.0" in d for d in ml), "ml extra must pin numpy<2.0"
    assert any("opencv" in d for d in ml), "ml extra needs an OpenCV for the USB camera"


def _modules_after_import(stmt: str) -> set[str]:
    code = f"import sys\n{stmt}\nprint('\\n'.join(sorted(sys.modules)))"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return set(proc.stdout.split())


def _ml_leaks(mods: set[str]) -> set[str]:
    return {m for m in mods if m == "" or m.split(".", 1)[0] in _ML_NAMES}


def test_core_cli_does_not_import_ml_deps() -> None:
    leaked = _ml_leaks(_modules_after_import("import pibot.cli"))
    assert not leaked, f"pibot.cli pulled in ML deps (must be lazy): {leaked}"


def test_agent_app_does_not_import_ml_deps() -> None:
    leaked = _ml_leaks(_modules_after_import("import agent.app"))
    assert not leaked, f"agent.app pulled in ML deps (must be lazy): {leaked}"
