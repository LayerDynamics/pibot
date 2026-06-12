"""T4.8 — pibot agent status|start|stop|logs: on-Pi command construction over SSH."""

from __future__ import annotations

from pibot import agent_ctl
from pibot.config import Config
from pibot.inventory import Inventory, InventoryRecord


def _inv() -> Inventory:
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    return inv


def _capture(monkeypatch) -> dict:
    seen: dict = {}

    def fake_run(target, command, **kwargs):
        seen["target"] = target
        seen["command"] = command
        seen["user"] = kwargs.get("explicit_user")
        return 0

    monkeypatch.setattr(agent_ctl.commands, "run", fake_run)
    return seen


def _joined(seen: dict) -> str:
    return " ".join(seen["command"])


def test_start_launches_agent_module(monkeypatch) -> None:
    seen = _capture(monkeypatch)
    assert agent_ctl.start("pibot", cfg=Config(), inventory=_inv(), user="ubuntu") == 0
    cmd = _joined(seen)
    assert "-m agent" in cmd
    assert "nohup" in cmd
    assert seen["user"] == "ubuntu"


def test_stop_kills_agent(monkeypatch) -> None:
    seen = _capture(monkeypatch)
    agent_ctl.stop("pibot", cfg=Config(), inventory=_inv())
    assert "pkill" in _joined(seen)
    assert "agent" in _joined(seen)


def test_status_curls_healthz_on_configured_port(monkeypatch) -> None:
    seen = _capture(monkeypatch)
    agent_ctl.status("pibot", cfg=Config(agent_bind="127.0.0.1:8787"), inventory=_inv())
    cmd = _joined(seen)
    assert "curl" in cmd
    assert "8787/healthz" in cmd


def test_logs_tails_the_log(monkeypatch) -> None:
    seen = _capture(monkeypatch)
    agent_ctl.logs("pibot", cfg=Config(), inventory=_inv(), lines=120)
    cmd = _joined(seen)
    assert "tail -n 120" in cmd
    assert "pibotd.log" in cmd
