"""Enumerate block devices and refuse to flash anything we shouldn't.

The single most important function here is :func:`assert_safe_target`: before any
write, it refuses the system disk, the internal disk, anything mounted at ``/``, and
(when an expectation is supplied) any device whose size or model doesn't match the
intended target. Combined with ``--confirm``/``--dry-run`` upstream, this is what
prevents ``pibot flash`` from destroying the developer's own machine.
"""

from __future__ import annotations

import json
import plistlib
from collections.abc import Callable
from dataclasses import dataclass, field
from platform import system as platform_system

from pibot.errors import PibotError

# A device whose size is within this fraction of the expected size is accepted
# (USB/SD reported capacity routinely differs from the nominal marketing size).
_SIZE_TOLERANCE = 0.25

RunFn = Callable[[list[str]], bytes]


@dataclass
class BlockDevice:
    node: str
    size_bytes: int
    model: str
    removable: bool
    internal: bool
    mountpoints: list[str] = field(default_factory=list)
    is_system: bool = False

    @property
    def size_gb(self) -> float:
        return self.size_bytes / 1_000_000_000


# ---- parsing -------------------------------------------------------------


def parse_macos_info(plist_bytes: bytes) -> BlockDevice:
    """Parse one ``diskutil info -plist <node>`` document."""
    info = plistlib.loads(plist_bytes)
    mount = info.get("MountPoint") or ""
    mountpoints = [mount] if mount else []
    return BlockDevice(
        node=info.get("DeviceNode", ""),
        size_bytes=int(info.get("Size", 0)),
        model=info.get("MediaName", "") or "",
        removable=bool(info.get("RemovableMedia", False)),
        internal=bool(info.get("Internal", False)),
        mountpoints=mountpoints,
        is_system=(mount == "/"),
    )


def parse_macos_whole_disks(plist_bytes: bytes) -> list[str]:
    """Return ``/dev/diskN`` nodes from ``diskutil list -plist``."""
    data = plistlib.loads(plist_bytes)
    return [f"/dev/{name}" for name in data.get("WholeDisks", [])]


def _collect_mounts(node: dict) -> list[str]:
    mounts: list[str] = []
    if node.get("mountpoint"):
        mounts.append(node["mountpoint"])
    for child in node.get("children", []):
        mounts.extend(_collect_mounts(child))
    return mounts


def parse_linux_lsblk(json_text: str) -> list[BlockDevice]:
    """Parse ``lsblk -J -b -o NAME,SIZE,MODEL,RM,TYPE,MOUNTPOINT`` output."""
    data = json.loads(json_text)
    out: list[BlockDevice] = []
    for node in data.get("blockdevices", []):
        if node.get("type") not in (None, "disk"):
            continue
        mounts = _collect_mounts(node)
        out.append(
            BlockDevice(
                node=f"/dev/{node['name']}",
                size_bytes=int(node.get("size", 0)),
                model=(node.get("model") or "").strip(),
                removable=bool(node.get("rm", False)),
                internal=False,  # lsblk has no reliable internal flag; rely on is_system
                mountpoints=mounts,
                is_system=any(m == "/" or m.startswith("/boot") for m in mounts),
            )
        )
    return out


# ---- enumeration ---------------------------------------------------------


def _default_run(argv: list[str]) -> bytes:
    import subprocess

    return subprocess.run(argv, capture_output=True, timeout=30).stdout


def enumerate_devices(run: RunFn | None = None, system: str | None = None) -> list[BlockDevice]:
    """Enumerate whole block devices on this host (or via an injected ``run``)."""
    run = run or _default_run
    system = system or platform_system()
    if system == "Darwin":
        nodes = parse_macos_whole_disks(run(["diskutil", "list", "-plist"]))
        return [parse_macos_info(run(["diskutil", "info", "-plist", node])) for node in nodes]
    text = run(["lsblk", "-J", "-b", "-o", "NAME,SIZE,MODEL,RM,TYPE,MOUNTPOINT"]).decode(
        "utf-8", "replace"
    )
    return parse_linux_lsblk(text)


# ---- the guard -----------------------------------------------------------


def assert_safe_target(
    device: BlockDevice,
    *,
    expected_size: int | None = None,
    expected_model: str | None = None,
) -> None:
    """Raise PibotError unless ``device`` is a safe external flashing target."""
    if device.is_system or "/" in device.mountpoints:
        raise PibotError(f"refusing to write to the system disk {device.node}")
    if device.internal:
        raise PibotError(
            f"refusing to write to internal disk {device.node}; "
            "flashing targets must be external (USB/SD)"
        )
    if expected_size is not None and expected_size > 0:
        if abs(device.size_bytes - expected_size) / expected_size > _SIZE_TOLERANCE:
            raise PibotError(
                f"device {device.node} size {device.size_gb:.0f}GB does not match the "
                f"expected ~{expected_size / 1e9:.0f}GB target"
            )
    if expected_model and expected_model.lower() not in device.model.lower():
        raise PibotError(
            f"device {device.node} model {device.model!r} does not match expected "
            f"{expected_model!r}"
        )


def diff_new_device(before: list[BlockDevice], after: list[BlockDevice]) -> BlockDevice:
    """Return the single device present in ``after`` but not ``before``."""
    before_nodes = {d.node for d in before}
    fresh = [d for d in after if d.node not in before_nodes]
    if not fresh:
        raise PibotError("no new block device appeared")
    if len(fresh) > 1:
        raise PibotError(
            f"ambiguous: {len(fresh)} new devices appeared ({', '.join(d.node for d in fresh)})"
        )
    return fresh[0]
