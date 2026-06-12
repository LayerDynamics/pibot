"""Build and upload Arduino firmware via ``arduino-cli``.

Pure argv builders plus thin runners. The reference firmware sketch and its
protocol live under ``firmware/`` (added in milestone M3); this module is the host
side that compiles and flashes it to the connected Arduino.
"""

from __future__ import annotations

import glob
import os
from collections.abc import Callable

from pibot.errors import PibotError
from pibot.provision import tools

RunFn = Callable[[list[str]], int]

# Default ArduinoOTA listen port on the ESP32.
OTA_PORT = 3232


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


# ---- OTA (wireless) flashing ---------------------------------------------


def find_espota(vendor: str | None = None) -> str:
    """Locate the OTA upload tool ``espota.py``, preferring the ``vendor`` core's copy.

    Several cores ship an ``espota.py`` (esp32, rp2040, …); ``vendor`` (the fqbn's first
    field, e.g. ``esp32``) picks the matching one rather than whichever sorts last.
    """
    roots = [
        os.path.expanduser("~/Library/Arduino15"),  # macOS
        os.path.expanduser("~/.arduino15"),  # Linux / Raspberry Pi
    ]
    patterns: list[str] = []
    if vendor:
        patterns += [
            os.path.join(r, "packages", vendor, "hardware", "*", "*", "tools", "espota.py")
            for r in roots
        ]
    patterns += [
        os.path.join(r, "packages", "*", "hardware", "*", "*", "tools", "espota.py") for r in roots
    ]
    for pattern in patterns:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]  # newest core version of the preferred vendor
    raise PibotError(
        "espota.py not found — install the ESP32 core (arduino-cli core install esp32:esp32)"
    )


def ota_argv(
    espota: str, host: str, bin_path: str, *, port: int = OTA_PORT, password: str = ""
) -> list[str]:
    """Build the ``espota.py`` argv that pushes ``bin_path`` to ``host`` over WiFi."""
    argv = ["python3", espota, "-i", host, "-p", str(port), "-f", bin_path, "-r"]
    if password:
        argv += ["-a", password]
    return argv


def flash_ota(
    sketch: str,
    *,
    fqbn: str,
    host: str,
    port: int = OTA_PORT,
    password: str = "",
    binary: str | None = None,
    output_dir: str | None = None,
    espota_path: str | None = None,
    compile_run: RunFn | None = None,
    espota_run: RunFn | None = None,
    dry_run: bool = False,
) -> int:
    """Compile ``sketch`` and flash it to ``host`` **over WiFi** (ESP32 OTA) — no USB."""
    bin_ = binary or tools.require_tool("arduino-cli")
    out = output_dir or _mkbuilddir()
    crun = compile_run or _default_run
    rc = crun([bin_, "compile", "--fqbn", fqbn, "--output-dir", out, sketch])
    if rc != 0:
        raise PibotError(f"arduino-cli compile failed (exit {rc})")
    bin_path = os.path.join(out, os.path.basename(sketch.rstrip("/")) + ".ino.bin")
    espota = espota_path or find_espota(fqbn.split(":")[0])
    argv = ota_argv(espota, host, bin_path, port=port, password=password)
    if dry_run:
        from pibot.connection import runner

        return runner.preview(argv, label=f"firmware flash (ota -> {host})")
    rc = (espota_run or _default_run)(argv)
    if rc != 0:
        raise PibotError(f"OTA (wireless) flash to {host} failed (exit {rc})")
    return rc


def _mkbuilddir() -> str:  # pragma: no cover - thin tempdir glue
    import tempfile

    return tempfile.mkdtemp(prefix="pibot-fw-")
