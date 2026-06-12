"""T2.6 — clone/restore the Pi's NVMe over SSH."""

from __future__ import annotations

import pytest

from pibot.config import Config
from pibot.errors import PibotError
from pibot.inventory import Inventory, InventoryRecord
from pibot.provision import clone


def _inv() -> Inventory:
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    return inv


def test_clone_builds_dd_gzip_pipeline(tmp_path) -> None:
    seen = {}

    def fake_stream(argv, path):
        seen["argv"] = argv
        seen["path"] = path
        return 0

    out = tmp_path / "backup.img.gz"
    rc = clone.clone(
        "pibot",
        str(out),
        cfg=Config(),
        inventory=_inv(),
        user="ubuntu",
        device="/dev/nvme0n1",
        stream_to_file=fake_stream,
    )
    assert rc == 0
    remote = seen["argv"][-1]
    assert "dd if=/dev/nvme0n1" in remote
    assert "gzip" in remote
    assert "ubuntu@192.168.1.99" in seen["argv"]
    assert seen["path"] == str(out)


def test_restore_requires_confirm(tmp_path) -> None:
    img = tmp_path / "backup.img.gz"
    img.write_bytes(b"x")
    with pytest.raises(PibotError, match="confirm"):
        clone.restore(
            "pibot",
            str(img),
            cfg=Config(),
            inventory=_inv(),
            user="ubuntu",
            device="/dev/nvme0n1",
            confirm=False,
        )


def test_restore_builds_gunzip_dd_pipeline(tmp_path) -> None:
    seen = {}
    img = tmp_path / "backup.img.gz"
    img.write_bytes(b"x")
    rc = clone.restore(
        "pibot",
        str(img),
        cfg=Config(),
        inventory=_inv(),
        user="ubuntu",
        device="/dev/nvme0n1",
        confirm=True,
        stream_from_file=lambda argv, path: seen.update(argv=argv, path=path) or 0,
    )
    assert rc == 0
    remote = seen["argv"][-1]
    assert "gunzip" in remote
    assert "dd of=/dev/nvme0n1" in remote


def test_restore_missing_image_raises(tmp_path) -> None:
    with pytest.raises(PibotError, match="not found|exist"):
        clone.restore(
            "pibot",
            str(tmp_path / "nope.gz"),
            cfg=Config(),
            inventory=_inv(),
            user="ubuntu",
            confirm=True,
            stream_from_file=lambda a, p: 0,
        )
