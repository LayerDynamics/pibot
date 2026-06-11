"""T5.1/T5.6 CLI wiring — ``deploy`` (sync+install / dry-run / rollback) and ``play`` dispatch."""

from __future__ import annotations

import pibot.cli as cli
from pibot.config import Config
from pibot.deploy.sync import DeployResult


class _Inv:
    def resolve(self, target: str) -> str:
        return "192.168.1.99"


def _ctx(monkeypatch, cfg: Config | None = None) -> None:
    monkeypatch.setattr(cli, "_context", lambda: (cfg or Config(), _Inv()))


def test_deploy_runs_sync_then_install(monkeypatch) -> None:
    seen: dict = {}
    _ctx(monkeypatch)
    monkeypatch.setattr(
        cli.deploy_sync,
        "deploy",
        lambda dest, **k: DeployResult("/opt/pibot/releases/x", ["agent/app.py"], True),
    )
    monkeypatch.setattr(
        cli.deploy_service, "install", lambda dest, **k: seen.update(install=dest) or 0
    )
    rc = cli.main(["deploy", "pibot", "--user", "pi", "--src", "/tmp"])
    assert rc == 0
    assert seen["install"] == "pi@192.168.1.99"


def test_deploy_dry_run_skips_install(monkeypatch) -> None:
    seen: dict = {}
    _ctx(monkeypatch)
    monkeypatch.setattr(
        cli.deploy_sync,
        "deploy",
        lambda dest, **k: DeployResult("/opt/pibot/releases/x", [], False),
    )
    monkeypatch.setattr(
        cli.deploy_service, "install", lambda *a, **k: seen.update(install=True) or 0
    )
    rc = cli.main(["deploy", "pibot", "--user", "pi", "--dry-run"])
    assert rc == 0
    assert "install" not in seen  # dry run computes the diff but never restarts


def test_deploy_rollback_dispatch(monkeypatch) -> None:
    seen: dict = {}
    _ctx(monkeypatch)
    monkeypatch.setattr(
        cli.deploy_service, "rollback", lambda dest, **k: seen.update(rollback=dest) or 0
    )
    rc = cli.main(["deploy", "pibot", "--user", "pi", "--rollback"])
    assert rc == 0
    assert seen["rollback"] == "pi@192.168.1.99"


def test_play_parses_sequence_and_drives(monkeypatch, tmp_path) -> None:
    seq = tmp_path / "wiggle.yaml"
    seq.write_text("- {at: 0.0, cmd: drive, args: {v: 0.5}}\n- {at: 1.0, cmd: stop}\n")
    captured: dict = {}
    _ctx(monkeypatch)

    def fake_drive(cfg, inv, target, steps, rate):
        captured.update(target=target, steps=steps, rate=rate)
        return 0

    monkeypatch.setattr(cli, "_drive_sequence", fake_drive)
    rc = cli.main(["play", "pibot", str(seq), "--rate", "5"])
    assert rc == 0
    assert captured["target"] == "pibot"
    assert [s.cmd for s in captured["steps"]] == ["drive", "stop"]
    assert captured["rate"] == 5
