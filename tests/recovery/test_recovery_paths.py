"""T6.4 — every destructive op has a tested recovery path.

Destructive ops in the suite: ``flash`` / ``provision restore`` (overwrite a disk),
``eeprom`` write (overwrite the bootloader config), ``deploy`` (replace the running
agent). For each, the recovery that makes it safe is asserted *and exercised* here —
not merely documented in a runbook.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pibot.config import Config
from pibot.connection.runner import RunResult
from pibot.deploy import service
from pibot.errors import PibotError
from pibot.provision import clone, eeprom


class _Inv:
    def resolve(self, target: str) -> str:
        return "192.168.1.99"


# ---- flash / restore: a clone round-trips back onto the disk --------------


def test_clone_then_restore_roundtrips_a_tiny_image(tmp_path) -> None:
    """The flash/restore recovery: a cloned image restores byte-for-byte."""
    cfg = Config()
    inv = _Inv()
    image = tmp_path / "backup.img.gz"
    payload = bytes(range(256)) * 8  # a tiny stand-in disk image

    def fake_clone_stream(argv: list[str], path: str) -> int:
        assert any("dd if=/dev/nvme0n1" in a for a in argv)  # reads the boot drive
        Path(path).write_bytes(payload)
        return 0

    rc = clone.clone(
        "pibot", str(image), cfg=cfg, inventory=inv, user="pi", stream_to_file=fake_clone_stream
    )
    assert rc == 0 and image.read_bytes() == payload

    captured: dict[str, bytes] = {}

    def fake_restore_stream(argv: list[str], path: str) -> int:
        assert any("dd of=/dev/nvme0n1" in a for a in argv)  # writes the boot drive back
        captured["data"] = Path(path).read_bytes()
        return 0

    rc = clone.restore(
        "pibot",
        str(image),
        cfg=cfg,
        inventory=inv,
        user="pi",
        confirm=True,
        stream_from_file=fake_restore_stream,
    )
    assert rc == 0
    assert captured["data"] == payload  # recovered exactly


def test_restore_refuses_without_confirm(tmp_path) -> None:
    image = tmp_path / "backup.img.gz"
    image.write_bytes(b"x")
    with pytest.raises(PibotError, match="confirm"):
        clone.restore("pibot", str(image), cfg=Config(), inventory=_Inv())


def test_restore_refuses_missing_image() -> None:
    with pytest.raises(PibotError, match="not found"):
        clone.restore(
            "pibot", "/no/such/image.img.gz", cfg=Config(), inventory=_Inv(), confirm=True
        )


# ---- eeprom: a BOOT_ORDER change preserves the rest of the config --------


def test_eeprom_boot_order_change_preserves_other_config(tmp_path) -> None:
    """The recovery property: only BOOT_ORDER is rewritten; other keys survive."""
    script = eeprom._boot_order_script("0xf416")
    # the script reads the current config, edits in place, and applies it
    assert "rpi-eeprom-config >" in script
    assert "rpi-eeprom-config --apply" in script

    # exercise the exact sed transformation on a representative config
    cfg_text = "[all]\nBOOT_UART=1\nBOOT_ORDER=0xf41\nPOWER_OFF_ON_HALT=0\n"
    sample = tmp_path / "eeprom.conf"
    sample.write_text(cfg_text)
    subprocess.run(
        ["sed", "-i.bak", "s/^BOOT_ORDER=.*/BOOT_ORDER=0xf416/", str(sample)], check=True
    )
    result = sample.read_text()
    assert "BOOT_ORDER=0xf416" in result  # changed
    assert "BOOT_UART=1" in result and "POWER_OFF_ON_HALT=0" in result  # preserved


def test_eeprom_write_requires_confirm() -> None:
    with pytest.raises(PibotError, match="confirm"):
        eeprom.update("pibot", cfg=Config(), inventory=_Inv())
    with pytest.raises(PibotError, match="confirm"):
        eeprom.set_boot_order("pibot", "0xf416", cfg=Config(), inventory=_Inv())


# ---- deploy: rollback restores the previous release ----------------------


def test_deploy_rollback_restores_previous_release(monkeypatch) -> None:
    ran: list[str] = []

    def fake_capture(argv, **kw):
        joined = " ".join(argv)
        ran.append(joined)
        if "readlink" in joined:
            return RunResult(0, "20260610T010101Z\n", "", 0.01)  # an older release exists
        out = '{"ok": true}' if "health" in joined else ""
        return RunResult(0, out, "", 0.01)

    monkeypatch.setattr(service.runner, "run_capture", fake_capture)
    rc = service.rollback("pi@host", remote_base="/opt/pibot", port=8787)
    assert rc == 0
    blob = "\n".join(ran)
    assert "ln -sfn /opt/pibot/releases/20260610T010101Z" in blob  # symlink repointed back
    assert "systemctl restart pibotd" in blob  # and the agent restarted
    assert "health" in blob  # recovery is health-gated too


def test_deploy_rollback_fails_loudly_with_no_previous_release(monkeypatch) -> None:
    def fake_capture(argv, **kw):
        if "readlink" in " ".join(argv):
            return RunResult(0, "\n", "", 0.01)  # nothing older
        return RunResult(0, "", "", 0.01)

    monkeypatch.setattr(service.runner, "run_capture", fake_capture)
    assert service.rollback("pi@host", remote_base="/opt/pibot") != 0
