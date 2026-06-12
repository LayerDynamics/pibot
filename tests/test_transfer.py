"""T1.4 — file transfer: rsync-first with scp fallback, and checksum verify."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pibot.config import Config
from pibot.connection import runner, transfer
from pibot.errors import ConnectionError
from pibot.inventory import Inventory, InventoryRecord


def _inv() -> Inventory:
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    return inv


def _ok_runner(captured):
    def fake(argv, **kwargs):
        captured.append(argv)
        return runner.RunResult(0, "", "", 0.0)

    return fake


def test_push_uses_rsync_when_available(monkeypatch) -> None:
    seen: list = []
    monkeypatch.setattr(transfer.runner, "run_capture", _ok_runner(seen))
    rc = transfer.push(
        "pibot",
        "/src/",
        "/remote/dst",
        cfg=Config(),
        inventory=_inv(),
        explicit_user="ubuntu",
        rsync_available=True,
    )
    assert rc == 0
    assert seen[0][0] == "rsync"
    assert seen[0][-1] == "ubuntu@192.168.1.99:/remote/dst"


def test_push_falls_back_to_scp(monkeypatch) -> None:
    seen: list = []
    monkeypatch.setattr(transfer.runner, "run_capture", _ok_runner(seen))
    transfer.push(
        "pibot",
        "/src",
        "/dst",
        cfg=Config(),
        inventory=_inv(),
        explicit_user="ubuntu",
        rsync_available=False,
    )
    assert seen[0][0] == "scp"


def test_pull_builds_remote_source(monkeypatch) -> None:
    seen: list = []
    monkeypatch.setattr(transfer.runner, "run_capture", _ok_runner(seen))
    transfer.pull(
        "pibot",
        "/remote/file",
        "/local/file",
        cfg=Config(),
        inventory=_inv(),
        explicit_user="ubuntu",
        rsync_available=True,
    )
    assert seen[0][-2] == "ubuntu@192.168.1.99:/remote/file"
    assert seen[0][-1] == "/local/file"


def test_push_returns_nonzero_on_transfer_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        transfer.runner, "run_capture", lambda argv, **k: runner.RunResult(23, "", "rsync err", 0.0)
    )
    rc = transfer.push("pibot", "/a", "/b", cfg=Config(), inventory=_inv(), explicit_user="u")
    assert rc == 23


def test_verify_matches(monkeypatch, tmp_path: Path) -> None:
    local = tmp_path / "f.bin"
    local.write_bytes(b"payload-123")
    digest = hashlib.sha256(b"payload-123").hexdigest()

    def fake(argv, **kwargs):
        # transfer succeeds; the verify sha256sum returns the matching digest
        if any("sha256sum" in a for a in argv):
            return runner.RunResult(0, f"{digest}  /remote/f.bin\n", "", 0.0)
        return runner.RunResult(0, "", "", 0.0)

    monkeypatch.setattr(transfer.runner, "run_capture", fake)
    rc = transfer.push(
        "pibot",
        str(local),
        "/remote/f.bin",
        cfg=Config(),
        inventory=_inv(),
        explicit_user="ubuntu",
        rsync_available=True,
        verify=True,
    )
    assert rc == 0


def test_verify_mismatch_raises(monkeypatch, tmp_path: Path) -> None:
    local = tmp_path / "f.bin"
    local.write_bytes(b"payload-123")

    def fake(argv, **kwargs):
        if any("sha256sum" in a for a in argv):
            return runner.RunResult(0, "deadbeef  /remote/f.bin\n", "", 0.0)
        return runner.RunResult(0, "", "", 0.0)

    monkeypatch.setattr(transfer.runner, "run_capture", fake)
    with pytest.raises(ConnectionError):
        transfer.push(
            "pibot",
            str(local),
            "/remote/f.bin",
            cfg=Config(),
            inventory=_inv(),
            explicit_user="ubuntu",
            rsync_available=True,
            verify=True,
        )
