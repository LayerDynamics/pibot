"""T1.7 — live SSH integration against a real robot.

These exercise the full stack with NO mocks: real ssh/scp/rsync to a real Pi. They
run only when ``PIBOT_TEST_HOST`` names a reachable robot that already trusts the
pibot key (run ``pibot keys install <host>`` once first). Otherwise they skip, so
CI and the default ``pytest`` run stay green without hardware.

    PIBOT_TEST_HOST=192.168.1.99 PIBOT_TEST_USER=ubuntu .venv/bin/pytest tests/integration
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

import pytest

from pibot.config import load_config
from pibot.connection import commands, transfer
from pibot.inventory import Inventory, InventoryRecord

_HOST = os.environ.get("PIBOT_TEST_HOST")
_USER = os.environ.get("PIBOT_TEST_USER")

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not _HOST, reason="set PIBOT_TEST_HOST to run live SSH tests"),
]


def _inventory() -> Inventory:
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip=_HOST or ""))
    return inv


def test_run_uptime_passwordless() -> None:
    rc = commands.run(
        "pibot", ["true"], cfg=load_config(), inventory=_inventory(), explicit_user=_USER
    )
    assert rc == 0, "passwordless `run` failed — is the pibot key installed on the host?"


def test_push_pull_roundtrip_preserves_checksum(tmp_path: Path) -> None:
    cfg = load_config()
    inv = _inventory()
    payload = secrets.token_bytes(4096)
    local = tmp_path / "up.bin"
    local.write_bytes(payload)
    remote = f"/tmp/pibot-it-{secrets.token_hex(6)}.bin"
    back = tmp_path / "down.bin"

    assert (
        transfer.push(
            "pibot", str(local), remote, cfg=cfg, inventory=inv, explicit_user=_USER, verify=True
        )
        == 0
    )
    assert (
        transfer.pull("pibot", remote, str(back), cfg=cfg, inventory=inv, explicit_user=_USER) == 0
    )
    assert hashlib.sha256(back.read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()

    # Clean up the remote temp file.
    commands.run("pibot", ["rm", "-f", remote], cfg=cfg, inventory=inv, explicit_user=_USER)
