"""T2.2/T2.3 — image flashing: rpi-imager argv, macOS raw-disk handling, the
removable-media path, and the rpiboot mass-storage orchestration."""

from __future__ import annotations

import pytest

from pibot.errors import PibotError
from pibot.provision import devices, flash, imager


def _dev(node="/dev/disk4", **kw) -> devices.BlockDevice:
    base = dict(
        size_bytes=256_000_000_000,
        model="NVMe",
        removable=True,
        internal=False,
        mountpoints=[],
        is_system=False,
    )
    base.update(kw)
    return devices.BlockDevice(node=node, **base)


# ---- imager argv ---------------------------------------------------------


def test_imager_argv_minimal() -> None:
    argv = imager.imager_argv("os.img.xz", "/dev/rdisk4", binary="rpi-imager")
    assert argv[:2] == ["rpi-imager", "--cli"]
    assert argv[-2:] == ["os.img.xz", "/dev/rdisk4"]


def test_imager_argv_with_sha256_and_flags() -> None:
    argv = imager.imager_argv(
        "os.img", "/dev/rdisk4", binary="rpi-imager", sha256="abc", disable_verify=True
    )
    assert "--sha256" in argv and argv[argv.index("--sha256") + 1] == "abc"
    assert "--disable-verify" in argv


def test_macos_raw_device() -> None:
    assert imager.macos_raw_device("/dev/disk4") == "/dev/rdisk4"
    assert imager.macos_raw_device("/dev/sda") == "/dev/sda"  # linux untouched


# ---- removable-media flash ----------------------------------------------


def test_flash_dry_run_prints_steps_and_writes_nothing(capsys) -> None:
    ran: list = []
    rc = flash.flash_to_device(
        "os.img.xz",
        "/dev/disk4",
        dry_run=True,
        system="Darwin",
        enumerate_fn=lambda: [_dev()],
        run=lambda a: ran.append(a) or 0,
        imager_binary="rpi-imager",
    )
    assert rc == 0
    assert ran == []  # nothing executed
    out = capsys.readouterr().out
    assert "unmountDisk" in out
    assert "/dev/rdisk4" in out  # macOS raw device used


def test_flash_macos_unmounts_then_writes_rdisk() -> None:
    ran: list = []
    flash.flash_to_device(
        "os.img.xz",
        "/dev/disk4",
        system="Darwin",
        enumerate_fn=lambda: [_dev()],
        run=lambda a: ran.append(a) or 0,
        imager_binary="rpi-imager",
    )
    assert ran[0][:2] == ["diskutil", "unmountDisk"]
    assert ran[1][0] == "rpi-imager"
    assert ran[1][-1] == "/dev/rdisk4"


def test_flash_refuses_system_disk() -> None:
    with pytest.raises(PibotError, match="system|internal"):
        flash.flash_to_device(
            "os.img",
            "/dev/disk0",
            system="Darwin",
            enumerate_fn=lambda: [_dev(node="/dev/disk0", internal=True, removable=False)],
            run=lambda a: 0,
            imager_binary="rpi-imager",
        )


def test_flash_unknown_device_raises() -> None:
    with pytest.raises(PibotError, match="not found"):
        flash.flash_to_device(
            "os.img",
            "/dev/disk9",
            system="Darwin",
            enumerate_fn=lambda: [_dev(node="/dev/disk4")],
            run=lambda a: 0,
            imager_binary="rpi-imager",
        )


# ---- rpiboot mass-storage flow ------------------------------------------


def test_flash_via_rpiboot_orchestration() -> None:
    before = [_dev(node="/dev/disk0", internal=True, removable=False)]
    after = before + [_dev(node="/dev/disk4")]
    enums = iter([before, after])
    ran: list = []
    flashed: dict = {}

    def fake_flash(image, node, **kwargs):
        flashed["image"] = image
        flashed["node"] = node
        return 0

    rc = flash.flash_via_rpiboot(
        "os.img.xz",
        enumerate_fn=lambda: next(enums),
        rpiboot_run=lambda a: ran.append(a) or 0,
        rpiboot_binary="rpiboot",
        flash_fn=fake_flash,
        poll_delay=0,
    )
    assert rc == 0
    assert ran[0] == ["rpiboot", "-d", "mass-storage-gadget64"]
    assert flashed["node"] == "/dev/disk4"


def test_flash_via_rpiboot_no_device_raises() -> None:
    same = [_dev(node="/dev/disk0", internal=True)]
    with pytest.raises(PibotError, match="no new|power button"):
        flash.flash_via_rpiboot(
            "os.img",
            enumerate_fn=lambda: same,
            rpiboot_run=lambda a: 0,
            rpiboot_binary="rpiboot",
            flash_fn=lambda *a, **k: 0,
            poll_attempts=2,
            poll_delay=0,
        )


def test_flash_via_rpiboot_dry_run(capsys) -> None:
    rc = flash.flash_via_rpiboot(
        "os.img",
        dry_run=True,
        enumerate_fn=lambda: [],
        rpiboot_binary="rpiboot",
        rpiboot_run=lambda a: 0,
        flash_fn=lambda *a, **k: 0,
    )
    assert rc == 0
    assert "power button" in capsys.readouterr().out.lower()
