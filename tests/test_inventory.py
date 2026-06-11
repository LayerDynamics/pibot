"""T0.4 — host inventory CRUD, persistence, and target resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from pibot.errors import InventoryError
from pibot.inventory import Inventory, InventoryRecord


def test_add_get_list_roundtrip(isolated_config_dir: str) -> None:
    inv = Inventory.load()
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99", mac="2CCF67386C20", pi=True))
    inv.save()

    reloaded = Inventory.load()
    rec = reloaded.get("pibot")
    assert rec is not None
    assert rec.ip == "192.168.1.99"
    assert rec.pi is True
    assert [r.alias for r in reloaded.list()] == ["pibot"]


def test_add_is_upsert_by_alias(isolated_config_dir: str) -> None:
    inv = Inventory.load()
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.50"))  # same alias -> replace
    assert len(inv.list()) == 1
    assert inv.get("pibot").ip == "192.168.1.50"


def test_remove(isolated_config_dir: str) -> None:
    inv = Inventory.load()
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    inv.remove("pibot")
    assert inv.get("pibot") is None
    with pytest.raises(InventoryError):
        inv.remove("ghost")


def test_set_alias_renames(isolated_config_dir: str) -> None:
    inv = Inventory.load()
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    inv.set_alias("pibot", "rover")
    assert inv.get("pibot") is None
    assert inv.get("rover").ip == "192.168.1.99"
    with pytest.raises(InventoryError):
        inv.set_alias("missing", "x")


def test_resolution_order(isolated_config_dir: str) -> None:
    inv = Inventory.load()
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    inv.add(InventoryRecord(alias="byname", hostname="rover.local"))
    # 1. alias -> its address (ip preferred)
    assert inv.resolve("pibot") == "192.168.1.99"
    # alias with only a hostname -> the hostname
    assert inv.resolve("byname") == "rover.local"
    # 2. raw IPv4 passes through
    assert inv.resolve("10.0.0.5") == "10.0.0.5"
    # 3. already-qualified / .local name passes through
    assert inv.resolve("thing.local") == "thing.local"
    # 4. bare name -> mDNS .local
    assert inv.resolve("freshpi") == "freshpi.local"


def test_resolution_rejects_blank(isolated_config_dir: str) -> None:
    inv = Inventory.load()
    with pytest.raises(InventoryError):
        inv.resolve("   ")


def test_load_skips_records_without_alias(isolated_config_dir: str) -> None:
    # A hand-edited file with a malformed (alias-less) record must not crash load.
    path = Path(isolated_config_dir) / "inventory.toml"
    path.write_text(
        '[[host]]\nip = "192.168.1.99"\nalias = "good"\n\n[[host]]\nip = "10.0.0.9"\n',
        encoding="utf-8",
    )
    inv = Inventory.load()
    assert [r.alias for r in inv.list()] == ["good"]
