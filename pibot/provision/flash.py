"""High-level flashing: removable media and the Pi-5 rpiboot mass-storage flow.

Every write goes through :func:`devices.assert_safe_target` first, and every path
supports ``dry_run`` (print the exact external commands, touch nothing). The rpiboot
flow reimages the Pi's onboard NVMe over USB-C without removing the drive: hold the
power button while connecting, ``rpiboot`` exposes the NVMe as a USB disk, and we
write to that.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from platform import system as platform_system

from pibot.errors import PibotError
from pibot.logging import get_logger
from pibot.provision import devices, firstboot, imager, tools

_log = get_logger("flash")

RunFn = Callable[[list[str]], int]
EnumFn = Callable[[], list[devices.BlockDevice]]
MountFn = Callable[[str], str]
UnmountFn = Callable[[str], None]


@dataclass
class FirstBootSpec:
    """Headless first-boot configuration applied to the boot partition after a flash."""

    hostname: str
    username: str
    ssh_authorized_keys: list[str] = field(default_factory=list)
    password_hash: str | None = None
    flavor: str | None = None  # "ubuntu" | "rpi-os" | None (auto-detect)


def _default_run(argv: list[str]) -> int:
    import subprocess

    return subprocess.run(argv).returncode


def _is_url(image: str) -> bool:
    return image.startswith(("http://", "https://"))


def _verify_file_sha256(path: str, expected: str) -> None:
    """Verify a local image file's SHA-256, raising :class:`PibotError` on mismatch.

    rpi-imager's ``--sha256`` checks the *decompressed* image, but callers pass the hash
    of the image FILE (e.g. an ``.xz``). The suite therefore verifies the file itself and
    does not hand the (differing) value to rpi-imager.
    """
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise PibotError(f"image SHA-256 mismatch for {path}: expected {expected}, got {actual}")
    _log.info("image SHA-256 verified for %s", path)


def _default_mount_boot(device_node: str) -> str:  # pragma: no cover - macOS/diskutil glue
    import plistlib
    import subprocess
    import time

    boot_part = f"{device_node}s1"
    # rpi-imager rewrites the partition table and may briefly eject / re-enumerate the
    # disk on completion, so the freshly-written boot partition is not always present the
    # instant the write returns. Re-read the disk and retry before giving up.
    last_err = ""
    for _ in range(10):
        subprocess.run(["diskutil", "mountDisk", device_node], capture_output=True)
        mounted = subprocess.run(["diskutil", "mount", boot_part], capture_output=True, text=True)
        if mounted.returncode == 0:
            info = plistlib.loads(
                subprocess.run(
                    ["diskutil", "info", "-plist", boot_part], capture_output=True
                ).stdout
            )
            mount = info.get("MountPoint")
            if mount:
                return str(mount)
        last_err = (mounted.stderr or mounted.stdout).strip()
        time.sleep(2)
    raise PibotError(
        f"could not mount boot partition {boot_part} after flashing "
        f"({last_err or 'disk not found'}). rpi-imager may have ejected the card — "
        "re-insert it and re-apply the first-boot config."
    )


def _default_unmount(device_node: str) -> None:  # pragma: no cover - macOS/diskutil glue
    import subprocess

    subprocess.run(["diskutil", "unmountDisk", device_node])


def apply_first_boot_to_device(
    device_node: str,
    spec: FirstBootSpec,
    *,
    mount_boot_fn: MountFn | None = None,
    unmount_fn: UnmountFn | None = None,
) -> None:
    """Mount the boot partition of ``device_node``, write first-boot config, unmount."""
    mount = (mount_boot_fn or _default_mount_boot)(device_node)
    try:
        firstboot.apply_first_boot(
            mount,
            hostname=spec.hostname,
            username=spec.username,
            ssh_authorized_keys=spec.ssh_authorized_keys,
            password_hash=spec.password_hash,
            flavor=spec.flavor,
        )
    finally:
        (unmount_fn or _default_unmount)(device_node)


def _find(devs: list[devices.BlockDevice], node: str) -> devices.BlockDevice:
    for dev in devs:
        if dev.node == node:
            return dev
    raise PibotError(f"device {node} not found among {[d.node for d in devs]}")


def _show(steps: list[list[str]]) -> None:
    for step in steps:
        print("DRY-RUN:", " ".join(step))


def flash_to_device(
    image: str,
    device_node: str,
    *,
    sha256: str | None = None,
    dry_run: bool = False,
    expected_size: int | None = None,
    expected_model: str | None = None,
    system: str | None = None,
    enumerate_fn: EnumFn | None = None,
    run: RunFn | None = None,
    imager_binary: str | None = None,
    first_boot: FirstBootSpec | None = None,
    mount_boot_fn: MountFn | None = None,
    unmount_fn: UnmountFn | None = None,
) -> int:
    """Write ``image`` to a removable ``device_node`` after safety checks."""
    system = system or platform_system()
    devs = (enumerate_fn or devices.enumerate_devices)()
    target_dev = _find(devs, device_node)
    devices.assert_safe_target(
        target_dev, expected_size=expected_size, expected_model=expected_model
    )

    binary = imager_binary or tools.require_tool("rpi-imager")
    steps: list[list[str]] = []
    if system == "Darwin":
        # Unmount the disk first. rpi-imager --cli is given the plain /dev/diskN node: it
        # matches its removable-drive allowlist by that name and does its own raw-device
        # write, so passing /dev/rdiskN makes it reject the target ("not in list of
        # removable volumes").
        steps.append(["diskutil", "unmountDisk", device_node])
    # rpi-imager's --sha256 verifies the *decompressed* image; ``sha256`` here is the hash
    # of the image FILE (e.g. the .xz), so we verify the file ourselves (below) and do not
    # pass the differing value to rpi-imager. Its own post-write read-back still runs.
    steps.append(imager.imager_argv(image, device_node, binary=binary))

    if dry_run:
        if sha256 and not _is_url(image):
            print(f"DRY-RUN: verify image file SHA-256 == {sha256}")
        _show(steps)
        if first_boot:
            print(
                f"DRY-RUN: apply first-boot config (hostname={first_boot.hostname}, "
                f"user={first_boot.username}, {len(first_boot.ssh_authorized_keys)} key(s))"
            )
        return 0

    if sha256 and not _is_url(image):
        _verify_file_sha256(image, sha256)

    runner = run or _default_run
    for step in steps:
        rc = runner(step)
        if rc != 0:
            raise PibotError(f"flash step failed (exit {rc}): {' '.join(step)}")
    _log.info("flashed %s to %s", image, device_node)

    if first_boot:
        apply_first_boot_to_device(
            device_node, first_boot, mount_boot_fn=mount_boot_fn, unmount_fn=unmount_fn
        )
        _log.info("applied first-boot config to %s", device_node)
    return 0


def flash_via_rpiboot(
    image: str,
    *,
    sha256: str | None = None,
    dry_run: bool = False,
    expected_size: int | None = None,
    expected_model: str | None = None,
    system: str | None = None,
    enumerate_fn: EnumFn | None = None,
    rpiboot_run: RunFn | None = None,
    rpiboot_binary: str | None = None,
    gadget_dir: str | None = None,
    flash_fn: Callable[..., int] | None = None,
    first_boot: FirstBootSpec | None = None,
    poll_attempts: int = 20,
    poll_delay: float = 1.0,
) -> int:
    """Reflash the Pi's onboard NVMe over USB-C via rpiboot mass-storage mode."""
    enumerate_fn = enumerate_fn or devices.enumerate_devices
    binary = rpiboot_binary or tools.require_tool("rpiboot")
    before = enumerate_fn()

    if dry_run:
        shown_gadget = gadget_dir or tools.resolve_gadget_dir(binary) or "mass-storage-gadget64"
        print("DRY-RUN: hold the Pi 5 power button while connecting USB-C, then:")
        print("DRY-RUN:", binary, "-d", shown_gadget)
        print("DRY-RUN: wait for the NVMe to enumerate, then rpi-imager writes", image)
        if first_boot:
            print(
                f"DRY-RUN: apply first-boot config (hostname={first_boot.hostname}, "
                f"user={first_boot.username}, {len(first_boot.ssh_authorized_keys)} key(s))"
            )
        return 0

    _log.info("hold the Pi 5 power button while connecting USB-C (no jumper on Pi 5)")
    # rpiboot needs the real gadget-files directory, not a bare name (resolved from the
    # rpiboot binary location; injectable for tests).
    resolved_gadget = gadget_dir or tools.require_gadget_dir(binary)
    rc = (rpiboot_run or _default_run)([binary, "-d", resolved_gadget])
    if rc != 0:
        raise PibotError(f"rpiboot failed (exit {rc}); was the power button held on connect?")

    new_device: devices.BlockDevice | None = None
    for _ in range(poll_attempts):
        try:
            new_device = devices.diff_new_device(before, enumerate_fn())
            break
        except PibotError:
            time.sleep(poll_delay)
    if new_device is None:
        raise PibotError(
            "no NVMe appeared after rpiboot — did you hold the power button while connecting?"
        )
    _log.info("Pi storage enumerated as %s", new_device.node)

    flasher = flash_fn or flash_to_device
    return flasher(
        image,
        new_device.node,
        sha256=sha256,
        expected_size=expected_size,
        expected_model=expected_model,
        system=system,
        first_boot=first_boot,
    )
