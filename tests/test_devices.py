"""T2.1 — block-device enumeration and the wrong-disk safety guard.

This is the module that stands between `pibot flash` and a destroyed Mac. The
guard logic is tested exhaustively; refusing the system/internal disk is the
load-bearing behaviour.
"""

from __future__ import annotations

import plistlib

import pytest

from pibot.errors import PibotError
from pibot.provision import devices


def _macos_info(
    node="/dev/disk4",
    size=32_000_000_000,
    model="Generic SD",
    internal=False,
    removable=True,
    mount="",
) -> bytes:
    return plistlib.dumps(
        {
            "DeviceNode": node,
            "Size": size,
            "MediaName": model,
            "Internal": internal,
            "RemovableMedia": removable,
            "MountPoint": mount,
        }
    )


def test_parse_macos_info() -> None:
    dev = devices.parse_macos_info(_macos_info(model="NVMe SSD", size=256_000_000_000))
    assert dev.node == "/dev/disk4"
    assert dev.size_bytes == 256_000_000_000
    assert dev.model == "NVMe SSD"
    assert dev.removable is True
    assert dev.internal is False
    assert dev.is_system is False


def test_parse_macos_info_marks_root_mount_as_system() -> None:
    dev = devices.parse_macos_info(_macos_info(mount="/"))
    assert dev.is_system is True
    assert "/" in dev.mountpoints


def test_parse_macos_whole_disks() -> None:
    payload = plistlib.dumps({"WholeDisks": ["disk0", "disk4"]})
    assert devices.parse_macos_whole_disks(payload) == ["/dev/disk0", "/dev/disk4"]


def test_parse_linux_lsblk() -> None:
    js = """
    {"blockdevices":[
      {"name":"sda","size":"500107862016","model":"Internal SSD","rm":false,"type":"disk",
       "mountpoint":null,"children":[{"name":"sda1","mountpoint":"/","type":"part"}]},
      {"name":"sdb","size":"31914983424","model":"Card Reader","rm":true,"type":"disk",
       "mountpoint":null,"children":[{"name":"sdb1","mountpoint":null,"type":"part"}]}
    ]}
    """
    devs = {d.node: d for d in devices.parse_linux_lsblk(js)}
    assert devs["/dev/sda"].is_system is True  # a child mounts /
    assert devs["/dev/sda"].size_bytes == 500107862016
    assert devs["/dev/sdb"].is_system is False
    assert devs["/dev/sdb"].removable is True


# ---- the guard -----------------------------------------------------------


def _dev(**kw) -> devices.BlockDevice:
    base = dict(
        node="/dev/disk4",
        size_bytes=32_000_000_000,
        model="Generic SD",
        removable=True,
        internal=False,
        mountpoints=[],
        is_system=False,
    )
    base.update(kw)
    return devices.BlockDevice(**base)


def test_guard_accepts_external_target() -> None:
    devices.assert_safe_target(_dev())  # no raise


def test_guard_refuses_system_disk() -> None:
    with pytest.raises(PibotError, match="system"):
        devices.assert_safe_target(_dev(is_system=True))


def test_guard_refuses_root_mounted_disk() -> None:
    with pytest.raises(PibotError):
        devices.assert_safe_target(_dev(mountpoints=["/"]))


def test_guard_refuses_internal_disk() -> None:
    with pytest.raises(PibotError, match="internal"):
        devices.assert_safe_target(_dev(internal=True, removable=False))


def test_guard_size_mismatch_refused() -> None:
    with pytest.raises(PibotError, match="size"):
        devices.assert_safe_target(_dev(size_bytes=8_000_000_000), expected_size=256_000_000_000)


def test_guard_size_within_tolerance_ok() -> None:
    devices.assert_safe_target(_dev(size_bytes=250_000_000_000), expected_size=256_000_000_000)


def test_guard_model_mismatch_refused() -> None:
    with pytest.raises(PibotError, match="model"):
        devices.assert_safe_target(_dev(model="Generic SD"), expected_model="NVMe")


def test_guard_model_match_ok() -> None:
    devices.assert_safe_target(_dev(model="Samsung NVMe SSD"), expected_model="nvme")


# ---- new-device diff (used after rpiboot enumerates the Pi) ---------------


def test_diff_new_device_finds_the_one_that_appeared() -> None:
    before = [_dev(node="/dev/disk0", internal=True)]
    after = [_dev(node="/dev/disk0", internal=True), _dev(node="/dev/disk4")]
    assert devices.diff_new_device(before, after).node == "/dev/disk4"


def test_diff_new_device_none_appeared_raises() -> None:
    same = [_dev(node="/dev/disk0")]
    with pytest.raises(PibotError, match="no new"):
        devices.diff_new_device(same, same)


def test_diff_new_device_ambiguous_raises() -> None:
    before = [_dev(node="/dev/disk0")]
    after = [_dev(node="/dev/disk0"), _dev(node="/dev/disk4"), _dev(node="/dev/disk5")]
    with pytest.raises(PibotError, match="ambiguous"):
        devices.diff_new_device(before, after)


def test_enumerate_macos_two_step(monkeypatch) -> None:
    list_pl = plistlib.dumps({"WholeDisks": ["disk0", "disk4"]})

    def fake_run(argv):
        if argv[:2] == ["diskutil", "list"]:
            return list_pl
        node = argv[-1]
        internal = node.endswith("disk0")
        return _macos_info(node=node, internal=internal, removable=not internal)

    devs = devices.enumerate_devices(run=fake_run, system="Darwin")
    assert [d.node for d in devs] == ["/dev/disk0", "/dev/disk4"]
    assert devs[0].internal is True
