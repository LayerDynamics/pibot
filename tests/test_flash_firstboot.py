"""First-boot config application wired into the flash flow."""

from __future__ import annotations

from pathlib import Path

from pibot import tomlio
from pibot.provision import devices, flash

KEY = "ssh-ed25519 AAAAKEY layerdynamics@proton.me"


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


def _spec() -> flash.FirstBootSpec:
    return flash.FirstBootSpec(
        hostname="pibot", username="ubuntu", ssh_authorized_keys=[KEY], flavor="ubuntu"
    )


def test_flash_applies_cloud_init_after_write(tmp_path: Path) -> None:
    boot = tmp_path / "boot"
    boot.mkdir()
    flash.flash_to_device(
        "ubuntu.img.xz",
        "/dev/disk4",
        system="Darwin",
        enumerate_fn=lambda: [_dev()],
        run=lambda a: 0,
        imager_binary="rpi-imager",
        first_boot=_spec(),
        mount_boot_fn=lambda node: str(boot),
        unmount_fn=lambda node: None,
    )
    user_data = (boot / "user-data").read_text()
    assert KEY in user_data
    assert "hostname: pibot" in user_data


def test_flash_dry_run_does_not_apply_first_boot(tmp_path: Path, capsys) -> None:
    boot = tmp_path / "boot"
    boot.mkdir()
    flash.flash_to_device(
        "ubuntu.img.xz",
        "/dev/disk4",
        system="Darwin",
        dry_run=True,
        enumerate_fn=lambda: [_dev()],
        run=lambda a: 0,
        imager_binary="rpi-imager",
        first_boot=_spec(),
        mount_boot_fn=lambda node: str(boot),
        unmount_fn=lambda node: None,
    )
    assert not (boot / "user-data").exists()
    assert "first-boot" in capsys.readouterr().out.lower()


def test_apply_first_boot_to_device_mounts_writes_unmounts(tmp_path: Path) -> None:
    boot = tmp_path / "boot"
    boot.mkdir()
    (boot / "config.txt").write_text("")  # -> rpi-os flavor when not forced
    events: list = []
    flash.apply_first_boot_to_device(
        "/dev/disk4",
        flash.FirstBootSpec(
            hostname="pibot", username="pi", ssh_authorized_keys=[KEY], password_hash="$6$h"
        ),
        mount_boot_fn=lambda node: events.append(("mount", node)) or str(boot),
        unmount_fn=lambda node: events.append(("unmount", node)),
    )
    assert events == [("mount", "/dev/disk4"), ("unmount", "/dev/disk4")]
    assert KEY in tomlio.load(boot / "custom.toml")["ssh"]["authorized_keys"]
