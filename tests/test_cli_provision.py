"""T2.* — CLI dispatch + safety gating for the provisioning commands."""

from __future__ import annotations

import pytest

from pibot import cli
from pibot.provision import eeprom


def test_flash_requires_confirm_or_dry_run() -> None:
    assert cli.main(["flash", "--device", "/dev/disk4", "--image", "os.img"]) == 2


def test_flash_device_dry_run_dispatch(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        cli.flash,
        "flash_to_device",
        lambda image, node, **k: seen.update(image=image, node=node, dry=k.get("dry_run")) or 0,
    )
    assert cli.main(["flash", "--device", "/dev/disk4", "--image", "os.img", "--dry-run"]) == 0
    assert seen == {"image": "os.img", "node": "/dev/disk4", "dry": True}


def test_flash_with_authorized_key_builds_first_boot(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        cli.flash,
        "flash_to_device",
        lambda image, node, **k: seen.update(fb=k.get("first_boot")) or 0,
    )
    rc = cli.main(
        [
            "flash",
            "--device",
            "/dev/disk4",
            "--image",
            "u.img",
            "--dry-run",
            "--os",
            "ubuntu",
            "--authorized-key",
            "ssh-ed25519 AAAA me",
        ]
    )
    assert rc == 0
    fb = seen["fb"]
    assert fb.flavor == "ubuntu"
    assert fb.username == "ubuntu"  # default user follows --os
    assert fb.ssh_authorized_keys == ["ssh-ed25519 AAAA me"]


def test_flash_authorized_key_file(monkeypatch, tmp_path) -> None:
    seen = {}
    keyfile = tmp_path / "id_ed25519.pub"
    keyfile.write_text("ssh-ed25519 AAAAFROMFILE me\n")
    monkeypatch.setattr(
        cli.flash,
        "flash_to_device",
        lambda image, node, **k: seen.update(fb=k.get("first_boot")) or 0,
    )
    cli.main(
        [
            "flash",
            "--device",
            "/dev/disk4",
            "--image",
            "u.img",
            "--dry-run",
            "--authorized-key-file",
            str(keyfile),
        ]
    )
    assert seen["fb"].ssh_authorized_keys == ["ssh-ed25519 AAAAFROMFILE me"]


def test_flash_first_boot_without_key_errors(monkeypatch) -> None:
    monkeypatch.setattr(cli.flash, "flash_to_device", lambda *a, **k: 0)
    rc = cli.main(
        [
            "flash",
            "--device",
            "/dev/disk4",
            "--image",
            "u.img",
            "--dry-run",
            "--hostname",
            "pibot",
        ]
    )
    assert rc == 2  # UsageError: first-boot requested but no key


def test_flash_nvme_target_uses_rpiboot(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        cli.flash, "flash_via_rpiboot", lambda image, **k: seen.update(i=image) or 0
    )
    assert cli.main(["flash", "--target", "nvme", "--image", "os.img", "--confirm"]) == 0
    assert seen["i"] == "os.img"


def test_flash_target_and_device_mutually_exclusive() -> None:
    # argparse rejects giving both -> raises SystemExit(2)
    with pytest.raises(SystemExit) as exc:
        cli.main(["flash", "--target", "nvme", "--device", "/dev/disk4", "--image", "x"])
    assert exc.value.code == 2


def test_eeprom_status_dispatch(monkeypatch) -> None:
    seen = {}
    # commands.run is mocked away, so no network and no user resolution happens.
    monkeypatch.setattr(eeprom.commands, "run", lambda t, cmd, **k: seen.update(cmd=cmd) or 0)
    assert cli.main(["eeprom", "pibot", "status", "--user", "ubuntu"]) == 0
    assert seen["cmd"] == ["rpi-eeprom-update"]


def test_eeprom_update_without_confirm_errors() -> None:
    assert cli.main(["eeprom", "pibot", "update", "--user", "ubuntu"]) == 1


def test_eeprom_boot_order_requires_value() -> None:
    assert cli.main(["eeprom", "pibot", "boot-order", "--user", "ubuntu", "--confirm"]) == 2


def test_provision_clone_dispatch(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        cli.clone,
        "clone",
        lambda target, to, **k: seen.update(target=target, to=to) or 0,
    )
    assert (
        cli.main(["provision", "clone", "pibot", "--to", "/tmp/b.img.gz", "--user", "ubuntu"]) == 0
    )
    assert seen == {"target": "pibot", "to": "/tmp/b.img.gz"}


def test_provision_restore_dispatch(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        cli.clone,
        "restore",
        lambda target, frm, **k: seen.update(confirm=k.get("confirm")) or 0,
    )
    assert (
        cli.main(
            ["provision", "restore", "pibot", "--from", "/tmp/b.img.gz", "--confirm", "--user", "u"]
        )
        == 0
    )
    assert seen["confirm"] is True


def test_firmware_build_dispatch(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(cli.firmware, "build", lambda sketch, **k: seen.update(s=sketch) or 0)
    assert (
        cli.main(["firmware", "build", "firmware/pibot_arduino", "--fqbn", "arduino:avr:uno"]) == 0
    )
    assert seen["s"] == "firmware/pibot_arduino"


def test_firmware_flash_dispatch(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        cli.firmware, "flash", lambda sketch, **k: seen.update(port=k.get("port")) or 0
    )
    assert (
        cli.main(["firmware", "flash", "fw", "--fqbn", "arduino:avr:uno", "--port", "/dev/ttyACM0"])
        == 0
    )
    assert seen["port"] == "/dev/ttyACM0"
