"""T0.6 — `pibot` CLI dispatch for `discover` and `inventory`."""

from __future__ import annotations

import json

import pytest

from pibot import discovery
from pibot.cli import main
from pibot.inventory import Inventory


def _pi_host():
    pf = discovery.get_pifinder()
    pi = pf.Host(ip="192.168.1.99", mac="2CCF67386C20", vendor="Raspberry Pi (Trading)")
    pi.is_pi = True
    pi.hostname = "pibot"
    return pi


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_no_command_exits_two() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_unknown_command_exits_two() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["bogus"])
    assert exc.value.code == 2


def test_discover_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(discovery, "scan", lambda **k: [("192.168.1.0/24", [_pi_host()])])
    rc = main(["discover", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["networks"][0]["network"] == "192.168.1.0/24"
    assert data["networks"][0]["raspberry_pis"][0]["ip"] == "192.168.1.99"


def test_discover_upserts_pis_into_inventory(monkeypatch, capsys) -> None:
    monkeypatch.setattr(discovery, "scan", lambda **k: [("192.168.1.0/24", [_pi_host()])])
    rc = main(["discover"])
    assert rc == 0
    rec = Inventory.load().get("pibot")
    assert rec is not None and rec.ip == "192.168.1.99"


def test_inventory_add_and_list_json(capsys) -> None:
    assert main(["inventory", "add", "pibot", "192.168.1.99"]) == 0
    assert main(["inventory", "add", "rover", "rover.local", "--user", "ubuntu"]) == 0
    capsys.readouterr()  # drain
    assert main(["inventory", "list", "--json"]) == 0
    hosts = {h["alias"]: h for h in json.loads(capsys.readouterr().out)["hosts"]}
    assert hosts["pibot"]["ip"] == "192.168.1.99"
    assert hosts["rover"]["hostname"] == "rover.local"
    assert hosts["rover"]["user"] == "ubuntu"


def test_inventory_rm_and_alias(capsys) -> None:
    main(["inventory", "add", "pibot", "192.168.1.99"])
    assert main(["inventory", "alias", "pibot", "rover"]) == 0
    assert Inventory.load().get("rover") is not None
    assert main(["inventory", "rm", "rover"]) == 0
    assert Inventory.load().get("rover") is None


def test_inventory_rm_unknown_returns_error_code(capsys) -> None:
    rc = main(["inventory", "rm", "ghost"])
    assert rc == 1  # PibotError.exit_code, not a crash


def test_global_json_flag_before_subcommand(capsys) -> None:
    main(["inventory", "add", "pibot", "192.168.1.99"])
    capsys.readouterr()
    assert main(["--json", "inventory", "list"]) == 0
    assert json.loads(capsys.readouterr().out)["hosts"][0]["alias"] == "pibot"
