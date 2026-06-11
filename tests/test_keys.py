"""T1.5 — SSH key provisioning: idempotent keygen + authorized_keys install."""

from __future__ import annotations

from pathlib import Path

from pibot import tomlio
from pibot.config import Config, config_dir
from pibot.connection import keys, runner
from pibot.inventory import Inventory, InventoryRecord


def _inv() -> Inventory:
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    return inv


def _fake_keygen(key_path: Path):
    def fake(argv, **kwargs):
        Path(key_path).write_text("PRIVATE")
        Path(str(key_path) + ".pub").write_text("ssh-ed25519 AAAAKEY pibot")
        return runner.RunResult(0, "", "", 0.0)

    return fake


def test_ensure_keypair_generates_when_absent(monkeypatch, tmp_path: Path) -> None:
    key = tmp_path / "pibot_ed25519"
    calls: list = []

    def fake(argv, **kwargs):
        calls.append(argv)
        return _fake_keygen(key)(argv, **kwargs)

    monkeypatch.setattr(keys.runner, "run_capture", fake)
    keys.ensure_keypair(key)
    assert key.exists() and Path(str(key) + ".pub").exists()
    assert calls[0][0] == "ssh-keygen"
    assert "ed25519" in calls[0]


def test_ensure_keypair_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    key = tmp_path / "pibot_ed25519"
    key.write_text("PRIV")
    Path(str(key) + ".pub").write_text("ssh-ed25519 AAAA pibot")
    calls: list = []
    monkeypatch.setattr(keys.runner, "run_capture", lambda *a, **k: calls.append(a) or None)
    keys.ensure_keypair(key)
    assert calls == []  # keygen NOT invoked when the pair already exists


def test_authorized_keys_command_is_idempotent_guarded() -> None:
    cmd = keys._authorized_keys_command("ssh-ed25519 AAAA pibot")
    assert "grep -qxF" in cmd  # only appends if not already present
    assert "authorized_keys" in cmd
    assert "ssh-ed25519 AAAA pibot" in cmd


def test_install_key_uses_password_auth_and_records_identity(monkeypatch, tmp_path: Path) -> None:
    key = tmp_path / "pibot_ed25519"
    monkeypatch.setattr(keys.runner, "run_capture", _fake_keygen(key))
    captured: list = []

    def fake_interactive(argv):
        captured.append(argv)
        return 0

    monkeypatch.setattr(keys.runner, "run_interactive", fake_interactive)
    rc = keys.install_key(
        "pibot", cfg=Config(), inventory=_inv(), key_path=key, explicit_user="ubuntu"
    )
    assert rc == 0
    argv = captured[0]
    assert "BatchMode=yes" not in argv  # password prompt must be allowed on first install
    assert "ubuntu@192.168.1.99" in argv
    assert "ssh-ed25519 AAAAKEY pibot" in argv[-1]
    # identity recorded so later commands use the key automatically
    saved = tomlio.load(config_dir() / "config.toml")
    assert saved["identity"] == str(key)
