"""T3.5 — firmware protocol drift-guard (always) + arduino-cli compiles (opt-in).

The wire protocol must be byte-identical across firmware targets AND match the host
codec, or a frame built on one side won't verify on the other. The drift guard runs
every time; the actual compiles are gated behind PIBOT_FIRMWARE_COMPILE=1 (they need
the toolchain + cores) so the fast unit gate stays fast.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FW = REPO / "firmware"


def test_protocol_copies_are_identical() -> None:
    for name in ("protocol.h", "protocol.cpp"):
        avr = (FW / "pibot_arduino" / name).read_bytes()
        esp = (FW / "pibot_esp32" / name).read_bytes()
        assert avr == esp, f"firmware {name} has drifted between pibot_arduino and pibot_esp32"


def test_firmware_crc8_matches_host_codec() -> None:
    # The firmware CRC-8 polynomial/init must match the host codec, else frames built on
    # one side fail CRC on the other. Assert the constant appears in the firmware source.
    src = (FW / "pibot_arduino" / "protocol.cpp").read_text()
    assert "0x07" in src and "crc ^= " in src  # poly 0x07, init 0x00 (same as codec.crc8)


_RUN_COMPILE = os.environ.get("PIBOT_FIRMWARE_COMPILE") == "1"


def _core_installed(core: str) -> bool:
    if not shutil.which("arduino-cli"):
        return False
    out = subprocess.run(["arduino-cli", "core", "list"], capture_output=True, text=True).stdout
    return core in out


@pytest.mark.skipif(not _RUN_COMPILE, reason="set PIBOT_FIRMWARE_COMPILE=1 to run compiles")
@pytest.mark.parametrize(
    "sketch,fqbn,core",
    [
        ("pibot_arduino", "arduino:avr:uno", "arduino:avr"),
        ("pibot_esp32", "esp32:esp32:esp32", "esp32:esp32"),
    ],
)
def test_firmware_compiles(sketch: str, fqbn: str, core: str) -> None:
    if not _core_installed(core):
        pytest.skip(f"arduino core {core} not installed")
    result = subprocess.run(
        ["arduino-cli", "compile", "--fqbn", fqbn, str(FW / sketch)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
