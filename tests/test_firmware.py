"""T2.7 — Arduino firmware build/upload via arduino-cli."""

from __future__ import annotations

from pathlib import Path

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


def test_build_raises_on_compile_failure() -> None:
    import pytest

    from pibot.errors import PibotError

    with pytest.raises(PibotError, match="compile failed"):
        firmware.build("sketch", fqbn="arduino:avr:uno", binary="arduino-cli", run=lambda argv: 2)


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


def test_flash_raises_on_upload_failure() -> None:
    import pytest

    from pibot.errors import PibotError

    with pytest.raises(PibotError, match="upload failed"):
        firmware.flash(
            "sketch",
            fqbn="arduino:avr:uno",
            port="/dev/ttyACM0",
            binary="arduino-cli",
            run=lambda argv: 1,
        )


def test_flash_dry_run_previews_without_uploading(capsys) -> None:
    ran = {"called": False}
    rc = firmware.flash(
        "sketch",
        fqbn="arduino:avr:uno",
        port="/dev/ttyACM0",
        binary="arduino-cli",
        run=lambda argv: ran.update(called=True) or 0,
        dry_run=True,
    )
    assert rc == 0
    assert ran["called"] is False  # nothing uploaded
    assert "arduino-cli upload" in capsys.readouterr().out


# ---- OTA (wireless) flashing ---------------------------------------------


def test_ota_argv_construction() -> None:
    argv = firmware.ota_argv("/x/espota.py", "192.168.1.117", "/tmp/fw.bin", port=3232)
    assert argv[0] == "python3" and argv[1] == "/x/espota.py"
    assert "-i" in argv and argv[argv.index("-i") + 1] == "192.168.1.117"
    assert argv[argv.index("-p") + 1] == "3232"
    assert argv[argv.index("-f") + 1] == "/tmp/fw.bin"
    assert "-a" not in argv  # no password -> no auth flag


def test_ota_argv_includes_password_when_set() -> None:
    argv = firmware.ota_argv("/x/espota.py", "host", "/tmp/fw.bin", password="s3cret")
    assert argv[argv.index("-a") + 1] == "s3cret"


def test_flash_ota_compiles_then_pushes_over_network(tmp_path) -> None:
    seen: dict = {}

    def fake_compile(argv):
        # arduino-cli compile --fqbn <fqbn> --output-dir <dir> <sketch>
        out = argv[argv.index("--output-dir") + 1]
        Path(out, "pibot_esp32.ino.bin").write_bytes(b"FW")  # build artifact in the real out dir
        seen["compiled"] = True
        return 0

    def fake_espota(argv):
        seen["espota"] = argv
        return 0

    rc = firmware.flash_ota(
        "firmware/pibot_esp32",
        fqbn="esp32:esp32:esp32",
        host="192.168.1.117",
        binary="arduino-cli",
        output_dir=str(tmp_path),
        espota_path="/x/espota.py",
        compile_run=fake_compile,
        espota_run=fake_espota,
    )
    assert rc == 0
    assert seen["compiled"]
    assert "192.168.1.117" in seen["espota"]
    assert seen["espota"][-1].endswith("pibot_esp32.ino.bin") or "pibot_esp32.ino.bin" in " ".join(
        seen["espota"]
    )


def test_flash_ota_dry_run_previews(tmp_path, capsys) -> None:
    (tmp_path / "pibot_esp32.ino.bin").write_bytes(b"FW")
    rc = firmware.flash_ota(
        "firmware/pibot_esp32",
        fqbn="esp32:esp32:esp32",
        host="192.168.1.117",
        binary="arduino-cli",
        output_dir=str(tmp_path),
        espota_path="/x/espota.py",
        compile_run=lambda argv: 0,
        espota_run=lambda argv: (_ for _ in ()).throw(AssertionError("must not run in dry-run")),
        dry_run=True,
    )
    assert rc == 0
    assert "192.168.1.117" in capsys.readouterr().out


def test_flash_ota_raises_when_compile_fails(tmp_path) -> None:
    import pytest

    from pibot.errors import PibotError

    with pytest.raises(PibotError, match="compile failed"):
        firmware.flash_ota(
            "firmware/pibot_esp32",
            fqbn="esp32:esp32:esp32",
            host="192.168.1.117",
            binary="arduino-cli",
            output_dir=str(tmp_path),
            espota_path="/x/espota.py",
            compile_run=lambda argv: 1,
            espota_run=lambda argv: 0,
        )
