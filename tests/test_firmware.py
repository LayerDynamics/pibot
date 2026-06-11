"""T2.7 — Arduino firmware build/upload via arduino-cli."""

from __future__ import annotations

from pibot.provision import firmware


def test_compile_argv() -> None:
    argv = firmware.compile_argv("firmware/pibot_arduino", "arduino:avr:uno", binary="arduino-cli")
    assert argv[:2] == ["arduino-cli", "compile"]
    assert argv[argv.index("--fqbn") + 1] == "arduino:avr:uno"
    assert argv[-1] == "firmware/pibot_arduino"


def test_upload_argv() -> None:
    argv = firmware.upload_argv(
        "firmware/pibot_arduino", "arduino:avr:uno", "/dev/ttyACM0", binary="arduino-cli"
    )
    assert argv[:2] == ["arduino-cli", "upload"]
    assert argv[argv.index("-p") + 1] == "/dev/ttyACM0"
    assert argv[argv.index("--fqbn") + 1] == "arduino:avr:uno"


def test_build_runs_compile(monkeypatch) -> None:
    seen = {}
    rc = firmware.build(
        "sketch",
        fqbn="arduino:avr:uno",
        binary="arduino-cli",
        run=lambda argv: seen.update(argv=argv) or 0,
    )
    assert rc == 0
    assert seen["argv"][1] == "compile"


def test_flash_runs_upload(monkeypatch) -> None:
    seen = {}
    rc = firmware.flash(
        "sketch",
        fqbn="arduino:avr:uno",
        port="/dev/ttyACM0",
        binary="arduino-cli",
        run=lambda argv: seen.update(argv=argv) or 0,
    )
    assert rc == 0
    assert seen["argv"][1] == "upload"
