"""File transfer to and from the robot: rsync when available, scp otherwise.

Optionally verifies a transferred *file* by comparing a local SHA-256 against the
remote ``sha256sum`` — cheap insurance that a deploy or backup actually landed
intact. Directory verification is out of scope here (the deploy milestone handles
release integrity differently).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from shutil import which

from pibot.config import Config
from pibot.connection import runner, sshcmd, user
from pibot.errors import ConnectionError
from pibot.inventory import Inventory
from pibot.logging import get_logger

_log = get_logger("transfer")


def _rsync_present(override: bool | None) -> bool:
    return override if override is not None else which("rsync") is not None


def _build(src: str, dst: str, identity: str | None, use_rsync: bool) -> list[str]:
    if use_rsync:
        return sshcmd.rsync_command(src, dst, identity=identity)
    return sshcmd.scp_command(src, dst, identity=identity)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_remote_file(
    local_path: str, remote_path: str, address: str, login: str, identity: str | None
) -> None:
    if not Path(local_path).is_file():
        _log.debug("verify skipped: %s is not a regular file", local_path)
        return
    argv = sshcmd.run_command(address, ["sha256sum", remote_path], user=login, identity=identity)
    result = runner.run_capture(argv)
    remote_digest = result.stdout.split()[0] if result.stdout.split() else ""
    local_digest = _sha256_file(local_path)
    if remote_digest != local_digest:
        raise ConnectionError(
            f"checksum mismatch for {remote_path}: local {local_digest}, remote {remote_digest}"
        )


def _resolve(
    target: str, cfg: Config, inventory: Inventory, explicit_user: str | None, identity: str | None
) -> tuple[str, str, str | None]:
    address = inventory.resolve(target)
    login = user.resolve_user(address, cfg, explicit=explicit_user)
    return address, login, (identity or cfg.identity)


def push(
    target: str,
    src: str,
    dst: str,
    *,
    cfg: Config,
    inventory: Inventory,
    explicit_user: str | None = None,
    identity: str | None = None,
    rsync_available: bool | None = None,
    verify: bool = False,
) -> int:
    """Copy a local ``src`` to ``dst`` on the robot. Returns the transfer exit code."""
    address, login, ident = _resolve(target, cfg, inventory, explicit_user, identity)
    remote = sshcmd.remote_destination(address, login, dst)
    argv = _build(src, remote, ident, _rsync_present(rsync_available))
    result = runner.run_capture(argv)
    if result.stdout:
        _log.debug("%s", result.stdout.rstrip())
    if result.exit_code != 0:
        if result.stderr:
            _log.error("%s", result.stderr.rstrip())
        return result.exit_code
    if verify:
        _verify_remote_file(src, dst, address, login, ident)
    return 0


def pull(
    target: str,
    src: str,
    dst: str,
    *,
    cfg: Config,
    inventory: Inventory,
    explicit_user: str | None = None,
    identity: str | None = None,
    rsync_available: bool | None = None,
    verify: bool = False,
) -> int:
    """Copy ``src`` from the robot to local ``dst``. Returns the transfer exit code."""
    address, login, ident = _resolve(target, cfg, inventory, explicit_user, identity)
    remote = sshcmd.remote_destination(address, login, src)
    argv = _build(remote, dst, ident, _rsync_present(rsync_available))
    result = runner.run_capture(argv)
    if result.stdout:
        _log.debug("%s", result.stdout.rstrip())
    if result.exit_code != 0:
        if result.stderr:
            _log.error("%s", result.stderr.rstrip())
        return result.exit_code
    if verify:
        _verify_remote_file(dst, src, address, login, ident)
    return 0
