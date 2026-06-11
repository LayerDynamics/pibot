"""M4 — CLI dispatch for monitor and agent management."""

from __future__ import annotations

from pibot import cli


def test_monitor_dispatch(monkeypatch) -> None:
    seen: dict = {}

    async def fake(target, **kwargs):
        seen.update(target=target, once=kwargs.get("once"), csv=kwargs.get("as_csv"))
        return 0

    monkeypatch.setattr(cli.monitor_mod, "monitor", fake)
    assert cli.main(["monitor", "pibot", "--once", "--csv"]) == 0
    assert seen == {"target": "pibot", "once": True, "csv": True}


def test_agent_status_dispatch(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(
        cli.agent_ctl, "status", lambda target, **k: seen.update(t=target, u=k.get("user")) or 0
    )
    assert cli.main(["agent", "status", "--user", "ubuntu", "pibot"]) == 0
    assert seen == {"t": "pibot", "u": "ubuntu"}


def test_agent_logs_passes_lines(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(
        cli.agent_ctl, "logs", lambda target, **k: seen.update(lines=k.get("lines")) or 0
    )
    assert cli.main(["agent", "logs", "pibot", "--lines", "99"]) == 0
    assert seen["lines"] == 99


def test_agent_start_dispatch(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(cli.agent_ctl, "start", lambda target, **k: seen.update(t=target) or 0)
    assert cli.main(["agent", "start", "pibot"]) == 0
    assert seen["t"] == "pibot"
