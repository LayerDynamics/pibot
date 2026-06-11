"""Provision SSH key authentication for the robot.

``keys install`` generates a dedicated ``pibot_ed25519`` keypair (once) and appends
its public key to the robot's ``authorized_keys`` — idempotently, so re-running never
duplicates the entry. The first install authenticates with a password (BatchMode off
so the prompt is shown); afterwards the recorded identity makes every command
passwordless.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from pibot import tomlio
from pibot.config import Config, config_dir
from pibot.connection import runner, sshcmd, user
from pibot.errors import ConnectionError
from pibot.inventory import Inventory
from pibot.logging import get_logger

_log = get_logger("keys")


def default_key_path() -> Path:
    """Path to the suite's dedicated private key (``~/.ssh/pibot_ed25519``)."""
    return Path.home() / ".ssh" / "pibot_ed25519"


def _public_path(key_path: Path) -> Path:
    return Path(str(key_path) + ".pub")


def ensure_keypair(key_path: Path) -> Path:
    """Create an ed25519 keypair at ``key_path`` if it does not already exist."""
    if key_path.exists() and _public_path(key_path).exists():
        return key_path
    key_path.parent.mkdir(parents=True, exist_ok=True)
    argv = ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_path), "-C", "pibot"]
    result = runner.run_capture(argv)
    if result.exit_code != 0:
        raise ConnectionError(f"ssh-keygen failed: {result.stderr.strip()}")
    return key_path


def read_public_key(key_path: Path) -> str:
    """Return the public-key line for ``key_path``."""
    return _public_path(key_path).read_text(encoding="utf-8").strip()


def _authorized_keys_command(public_key: str) -> str:
    quoted = shlex.quote(public_key)
    return (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
        "touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && "
        f"grep -qxF {quoted} ~/.ssh/authorized_keys || "
        f"printf '%s\\n' {quoted} >> ~/.ssh/authorized_keys"
    )


def _record_identity(key_path: Path) -> None:
    path = config_dir() / "config.toml"
    raw = tomlio.load(path)
    raw["identity"] = str(key_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tomlio.dump(raw, path)


def install_key(
    target: str,
    *,
    cfg: Config,
    inventory: Inventory,
    key_path: Path | None = None,
    explicit_user: str | None = None,
    identity: str | None = None,
) -> int:
    """Generate (if needed) and install the suite's public key on ``target``."""
    key_path = key_path or default_key_path()
    ensure_keypair(key_path)
    public_key = read_public_key(key_path)

    address = inventory.resolve(target)
    login = user.resolve_user(address, cfg, explicit=explicit_user)
    argv = [
        "ssh",
        *sshcmd.ssh_options(batch=False, identity=identity or cfg.identity),
        sshcmd.destination(address, login),
        _authorized_keys_command(public_key),
    ]
    _log.info("installing pibot key on %s (you may be prompted for the password)", address)
    rc = runner.run_interactive(argv)
    if rc == 0:
        _record_identity(key_path)
        _log.info("key installed; recorded identity %s", key_path)
    return rc
