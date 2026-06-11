"""T1.6 — SSH local port-forward tunnels."""

from __future__ import annotations

import pytest

from pibot.config import Config
from pibot.connection import tunnel
from pibot.errors import UsageError
from pibot.inventory import Inventory, InventoryRecord


def _inv() -> Inventory:
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    return inv


def test_parse_spec_full_form() -> None:
    assert tunnel.parse_spec("8787:127.0.0.1:8787") == "8787:127.0.0.1:8787"


def test_parse_spec_shorthand_defaults_loopback() -> None:
    assert tunnel.parse_spec("8787:8787") == "8787:127.0.0.1:8787"


@pytest.mark.parametrize("bad", ["", "abc", "8787:host", "x:y:z", "8787:host:notaport"])
def test_parse_spec_rejects_malformed(bad: str) -> None:
    with pytest.raises(UsageError):
        tunnel.parse_spec(bad)


def test_open_tunnel_builds_local_forward(monkeypatch) -> None:
    captured = {}

    def fake_interactive(argv):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(tunnel.runner, "run_interactive", fake_interactive)
    rc = tunnel.open_tunnel(
        "pibot", "8787:127.0.0.1:8787", cfg=Config(), inventory=_inv(), explicit_user="ubuntu"
    )
    assert rc == 0
    argv = captured["argv"]
    assert "-N" in argv and "-L" in argv
    assert argv[argv.index("-L") + 1] == "8787:127.0.0.1:8787"
    assert argv[-1] == "ubuntu@192.168.1.99"
