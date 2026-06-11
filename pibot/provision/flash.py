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
from platform import system as platform_system

from pibot.errors import PibotError
from pibot.logging import get_logger
from pibot.provision import devices, imager, tools

_log = get_logger("flash")

RunFn = Callable[[list[str]], int]
EnumFn = Callable[[], list[devices.BlockDevice]]


def _default_run(argv: list[str]) -> int:
    import subprocess

    return subprocess.run(argv).returncode


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
    write_node = device_node
    if system == "Darwin":
        steps.append(["diskutil", "unmountDisk", device_node])
        write_node = imager.macos_raw_device(device_node)
    steps.append(imager.imager_argv(image, write_node, binary=binary, sha256=sha256))

    if dry_run:
        _show(steps)
        return 0

    runner = run or _default_run
    for step in steps:
        rc = runner(step)
        if rc != 0:
            raise PibotError(f"flash step failed (exit {rc}): {' '.join(step)}")
    _log.info("flashed %s to %s", image, device_node)
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
    flash_fn: Callable[..., int] | None = None,
    poll_attempts: int = 20,
    poll_delay: float = 1.0,
) -> int:
    """Reflash the Pi's onboard NVMe over USB-C via rpiboot mass-storage mode."""
    enumerate_fn = enumerate_fn or devices.enumerate_devices
    binary = rpiboot_binary or tools.require_tool("rpiboot")
    before = enumerate_fn()

    if dry_run:
        print("DRY-RUN: hold the Pi 5 power button while connecting USB-C, then:")
        print("DRY-RUN:", binary, "-d", "mass-storage-gadget64")
        print("DRY-RUN: wait for the NVMe to enumerate, then rpi-imager writes", image)
        return 0

    _log.info("hold the Pi 5 power button while connecting USB-C (no jumper on Pi 5)")
    rc = (rpiboot_run or _default_run)([binary, "-d", "mass-storage-gadget64"])
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
    )
