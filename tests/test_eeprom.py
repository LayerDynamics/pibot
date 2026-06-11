"""T2.5 — Pi bootloader EEPROM management over SSH."""

from __future__ import annotations

import pytest

from pibot.config import Config
from pibot.errors import PibotError, UsageError
from pibot.inventory import Inventory, InventoryRecord
from pibot.provision import eeprom


def _inv() -> Inventory:
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    return inv


def test_validate_boot_order() -> None:
    assert eeprom.validate_boot_order("0xf416") == "0xf416"
    assert eeprom.validate_boot_order("0XF416") == "0xf416"
    for bad in ["f416", "0xZZ", "", "nvme"]:
        with pytest.raises(UsageError):
            eeprom.validate_boot_order(bad)


def test_status_runs_rpi_eeprom_update(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(eeprom.commands, "run", lambda target, cmd, **k: seen.update(cmd=cmd) or 0)
    assert eeprom.status("pibot", cfg=Config(), inventory=_inv(), user="ubuntu") == 0
    assert seen["cmd"] == ["rpi-eeprom-update"]


def test_update_requires_confirm() -> None:
    with pytest.raises(PibotError, match="confirm"):
        eeprom.update("pibot", cfg=Config(), inventory=_inv(), user="ubuntu", confirm=False)


def test_update_with_confirm_runs_sudo(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(eeprom.commands, "run", lambda t, cmd, **k: seen.update(cmd=cmd) or 0)
    eeprom.update("pibot", cfg=Config(), inventory=_inv(), user="ubuntu", confirm=True)
    assert seen["cmd"][:2] == ["sudo", "rpi-eeprom-update"]
    assert "-a" in seen["cmd"]


def test_set_boot_order_requires_confirm() -> None:
    with pytest.raises(PibotError, match="confirm"):
        eeprom.set_boot_order("pibot", "0xf416", cfg=Config(), inventory=_inv(), user="u")


def test_set_boot_order_applies_value(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(eeprom.commands, "run", lambda t, cmd, **k: seen.update(cmd=cmd) or 0)
    eeprom.set_boot_order("pibot", "0xf416", cfg=Config(), inventory=_inv(), user="u", confirm=True)
    script = " ".join(seen["cmd"])
    assert "BOOT_ORDER=0xf416" in script
    assert "rpi-eeprom-config" in script and "--apply" in script
