"""T1.3/T1.4/T1.5/T1.6 — CLI dispatch for the connection commands."""

from __future__ import annotations

from pibot import cli


def test_run_strips_double_dash_and_dispatches(monkeypatch) -> None:
    seen = {}

    def fake_run(target, command, **kwargs):
        seen["target"] = target
        seen["command"] = command
        return 0

    monkeypatch.setattr(cli.commands, "run", fake_run)
    assert cli.main(["run", "pibot", "--", "uptime", "-a"]) == 0
    assert seen["target"] == "pibot"
    assert seen["command"] == ["uptime", "-a"]  # leading "--" stripped


def test_run_without_command_is_usage_error() -> None:
    assert cli.main(["run", "pibot"]) == 2  # UsageError.exit_code


def test_connect_passes_explicit_user(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        cli.commands,
        "connect",
        lambda target, **k: seen.update(target=target, user=k.get("explicit_user")) or 0,
    )
    assert cli.main(["connect", "--user", "ubuntu", "pibot"]) == 0
    assert seen == {"target": "pibot", "user": "ubuntu"}


def test_push_dispatch_with_verify(monkeypatch) -> None:
    seen = {}

    def fake_push(target, src, dst, **kwargs):
        seen.update(target=target, src=src, dst=dst, verify=kwargs.get("verify"))
        return 0

    monkeypatch.setattr(cli.transfer, "push", fake_push)
    assert cli.main(["push", "pibot", "/a", "/b", "--verify"]) == 0
    assert seen == {"target": "pibot", "src": "/a", "dst": "/b", "verify": True}


def test_pull_forces_scp_with_no_rsync(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        cli.transfer,
        "pull",
        lambda target, src, dst, **k: seen.update(rsync=k.get("rsync_available")) or 0,
    )
    assert cli.main(["pull", "pibot", "/r", "/l", "--no-rsync"]) == 0
    assert seen["rsync"] is False


def test_keys_install_dispatch(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        cli.keys,
        "install_key",
        lambda target, **k: seen.update(target=target) or 0,
    )
    assert cli.main(["keys", "install", "pibot"]) == 0
    assert seen["target"] == "pibot"


def test_tunnel_dispatch(monkeypatch) -> None:
    seen = {}
    monkeypatch.setattr(
        cli.tunnel,
        "open_tunnel",
        lambda target, spec, **k: seen.update(target=target, spec=spec) or 0,
    )
    assert cli.main(["tunnel", "pibot", "8787:8787"]) == 0
    assert seen == {"target": "pibot", "spec": "8787:8787"}
