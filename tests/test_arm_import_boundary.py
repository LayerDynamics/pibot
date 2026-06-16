"""M-ARM-4 task 4.3 — the `[ml]`/stdlib-light import boundary (NFR-2).

The heavy numeric stack (numpy, scipy, ikpy) lives behind the optional ``pibot[arm-ik]`` /
``pibot[ml]`` extras and must be pulled in **lazily** — only when FK/IK is actually used, never at
module *import* time. If a core module imported numpy/ikpy on load, the stdlib-light CLI and agent
would drag the whole numeric stack into every robot/host process.

Each case imports a core module in a **fresh interpreter** (so the assertion is independent of what
the rest of the pytest session already imported) and asserts neither ``numpy`` nor ``ikpy`` landed
in ``sys.modules``. These run in the default gate even with ``[arm-ik]`` installed — proving the
guard, not merely that the extra is absent.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

# Core modules that MUST import without dragging in the numeric stack.
_CORE_MODULES = ["pibot.arm", "pibot.arm.kinematics", "pibot.cli", "agent.app"]
# Heavy deps that may only be imported lazily (inside a function/method), never at module load.
_FORBIDDEN = ("numpy", "ikpy", "scipy")


@pytest.mark.parametrize("module", _CORE_MODULES)
def test_core_module_imports_without_the_numeric_stack(module: str) -> None:
    code = (
        "import sys, importlib;"
        f"importlib.import_module({module!r});"
        f"leaked=[m for m in {_FORBIDDEN!r} if m in sys.modules];"
        "print(','.join(leaked))"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    leaked = proc.stdout.strip()
    assert leaked == "", f"importing {module!r} leaked the numeric stack at module load: {leaked}"
