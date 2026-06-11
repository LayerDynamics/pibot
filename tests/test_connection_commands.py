"""T1.3 — `run` and `connect` orchestration (resolve -> build argv -> execute)."""

from __future__ import annotations

import json

from pibot.config import Config
from pibot.connection import commands, runner
from pibot.inventory import Inventory, InventoryRecord


def _inv() -> Inventory:
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    return inv


def test_run_resolves_target_and_returns_exit_code(monkeypatch) -> None:
    captured = {}

    def fake_capture(argv, **kwargs):
        captured["argv"] = argv
        return runner.RunResult(0, "up 3 days\n", "", 0.01)

    monkeypatch.setattr(commands.runner, "run_capture", fake_capture)
    rc = commands.run("pibot", ["uptime"], cfg=Config(), inventory=_inv(), explicit_user="ubuntu")
    assert rc == 0
    assert "ubuntu@192.168.1.99" in captured["argv"]
    assert captured["argv"][-1] == "uptime"


def test_run_json_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        commands.runner,
        "run_capture",
        lambda argv, **k: runner.RunResult(2, "out", "err", 0.5),
    )
    rc = commands.run(
        "pibot",
        ["false"],
        cfg=Config(),
        inventory=_inv(),
        explicit_user="ubuntu",
        as_json=True,
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["host"] == "192.168.1.99"
    assert payload["user"] == "ubuntu"
    assert payload["exit"] == 2
    assert payload["stdout"] == "out"
    assert payload["stderr"] == "err"


def test_run_uses_config_identity(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        commands.runner,
        "run_capture",
        lambda argv, **k: captured.update(argv=argv) or runner.RunResult(0, "", "", 0.0),
    )
    cfg = Config(identity="/home/me/.ssh/pibot_ed25519")
    commands.run("pibot", ["id"], cfg=cfg, inventory=_inv(), explicit_user="ubuntu")
    assert "/home/me/.ssh/pibot_ed25519" in captured["argv"]


def test_connect_builds_interactive_and_returns_code(monkeypatch) -> None:
    captured = {}

    def fake_interactive(argv):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(commands.runner, "run_interactive", fake_interactive)
    rc = commands.connect("pibot", cfg=Config(), inventory=_inv(), explicit_user="ubuntu")
    assert rc == 0
    assert "-t" in captured["argv"]
    assert captured["argv"][-1] == "ubuntu@192.168.1.99"
