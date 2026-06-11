"""Clone and restore the Pi's NVMe over SSH.

``clone`` streams a gzip-compressed image of the running drive back to a local file
(``sudo dd | gzip`` on the Pi, captured locally). ``restore`` reverses it and, because
it overwrites the boot drive, requires ``confirm=True``. Restore is the recovery path
that makes reflashing safe (see SPEC-1 NFR-7).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pibot.config import Config
from pibot.connection import sshcmd, user
from pibot.errors import PibotError
from pibot.inventory import Inventory
from pibot.logging import get_logger

_log = get_logger("clone")

StreamFn = Callable[[list[str], str], int]


def _stream_to_file(argv: list[str], path: str) -> int:  # pragma: no cover - thin I/O glue
    import subprocess

    with open(path, "wb") as fh:
        return subprocess.run(argv, stdout=fh).returncode


def _stream_from_file(argv: list[str], path: str) -> int:  # pragma: no cover - thin I/O glue
    import subprocess

    with open(path, "rb") as fh:
        return subprocess.run(argv, stdin=fh).returncode


def clone(
    target: str,
    to_file: str,
    *,
    cfg: Config,
    inventory: Inventory,
    user: str | None = None,
    device: str = "/dev/nvme0n1",
    shrink: bool = False,
    stream_to_file: StreamFn | None = None,
) -> int:
    """Stream a gzip image of the Pi's ``device`` into the local ``to_file``."""
    address = inventory.resolve(target)
    login = _resolve_user(address, cfg, user)
    if shrink:
        _log.info("shrink requested; image will be gzip-compressed on the fly")
    remote = f"sudo dd if={device} bs=4M status=none | gzip -c"
    argv = sshcmd.run_command(address, ["bash", "-lc", remote], user=login, identity=cfg.identity)
    _log.info("cloning %s:%s -> %s", address, device, to_file)
    return (stream_to_file or _stream_to_file)(argv, to_file)


def restore(
    target: str,
    from_file: str,
    *,
    cfg: Config,
    inventory: Inventory,
    user: str | None = None,
    device: str = "/dev/nvme0n1",
    confirm: bool = False,
    stream_from_file: StreamFn | None = None,
) -> int:
    """Restore a gzip image from ``from_file`` onto the Pi's ``device``."""
    if not Path(from_file).is_file():
        raise PibotError(f"image not found: {from_file}")
    if not confirm:
        raise PibotError(f"restore overwrites {device} on the robot; pass --confirm")
    address = inventory.resolve(target)
    login = _resolve_user(address, cfg, user)
    remote = f"gunzip -c | sudo dd of={device} bs=4M"
    argv = sshcmd.run_command(address, ["bash", "-lc", remote], user=login, identity=cfg.identity)
    _log.info("restoring %s -> %s:%s", from_file, address, device)
    return (stream_from_file or _stream_from_file)(argv, from_file)


def _resolve_user(address: str, cfg: Config, explicit: str | None) -> str:
    return user.resolve_user(address, cfg, explicit=explicit)
