"""T12.1.7 (toolchain-marked) — the bundled sidecar binary serves /api/health.

Builds the PyInstaller one-file sidecar via ``app/scripts/build-sidecar.sh``, runs it on a
loopback port, and verifies it answers the health probe with the per-launch token. Marked
``toolchain`` (needs PyInstaller + a real build), so it is deselected by default like the
firmware-compile tests; run explicitly with ``pytest -m toolchain tests/test_mc_packaging.py``.
"""

from __future__ import annotations

import platform
import re
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.toolchain

REPO = Path(__file__).resolve().parent.parent


def _triple() -> str:
    mach = platform.machine().lower()
    arch = "aarch64" if mach in ("arm64", "aarch64") else "x86_64"
    return f"{arch}-apple-darwin"


def test_built_sidecar_serves_health() -> None:
    subprocess.run(
        ["bash", str(REPO / "app" / "scripts" / "build-sidecar.sh")],
        check=True,
        cwd=REPO,
    )
    binary = REPO / "app" / "src-tauri" / "binaries" / f"pibot-mc-host-{_triple()}"
    assert binary.is_file(), f"sidecar binary not built at {binary}"

    proc = subprocess.Popen(
        [str(binary), "--port", "0", "--token", "tok"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        port: int | None = None
        deadline = time.time() + 30
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                continue
            m = re.match(r"PORT=(\d+)", line.strip())
            if m:
                port = int(m.group(1))
                break
        assert port, "sidecar did not report PORT= on stdout"

        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/health",
            headers={"Authorization": "Bearer tok"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
    finally:
        proc.terminate()
        proc.wait(timeout=5)
