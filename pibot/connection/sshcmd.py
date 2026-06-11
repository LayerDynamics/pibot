"""Pure construction of ssh/scp/rsync/tunnel argv lists.

No function here executes anything — they return argument vectors that
:mod:`pibot.connection.runner` runs. Defaults are chosen for unattended
automation: ``BatchMode=yes`` (never block on a password prompt) and
``StrictHostKeyChecking=accept-new`` (trust a first-seen host key but refuse a
changed one).
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence

_DEFAULT_CONNECT_TIMEOUT = 10


def ssh_options(
    *,
    batch: bool = True,
    connect_timeout: int = _DEFAULT_CONNECT_TIMEOUT,
    identity: str | None = None,
) -> list[str]:
    """Return the shared ``-o``/``-i`` option list for ssh and scp."""
    opts: list[str] = []
    if batch:
        opts += ["-o", "BatchMode=yes"]
    opts += ["-o", "StrictHostKeyChecking=accept-new"]
    if connect_timeout:
        opts += ["-o", f"ConnectTimeout={int(connect_timeout)}"]
    if identity:
        opts += ["-i", identity]
    return opts


def destination(host: str, user: str | None) -> str:
    """Format an ssh destination, ``user@host`` or bare ``host``."""
    return f"{user}@{host}" if user else host


def remote_destination(host: str, user: str | None, path: str) -> str:
    """Format an scp/rsync remote path, ``user@host:path`` or ``host:path``."""
    return f"{destination(host, user)}:{path}"


def _remote_command(command: str | Sequence[str]) -> str:
    """Render a remote command as a single shell-safe string."""
    if isinstance(command, str):
        return command
    return shlex.join(command)


def run_command(
    host: str,
    command: str | Sequence[str],
    *,
    user: str | None = None,
    identity: str | None = None,
    connect_timeout: int = _DEFAULT_CONNECT_TIMEOUT,
) -> list[str]:
    """Build argv to run a non-interactive remote command over ssh."""
    return [
        "ssh",
        *ssh_options(batch=True, connect_timeout=connect_timeout, identity=identity),
        destination(host, user),
        _remote_command(command),
    ]


def interactive_command(
    host: str,
    *,
    user: str | None = None,
    identity: str | None = None,
    connect_timeout: int = _DEFAULT_CONNECT_TIMEOUT,
) -> list[str]:
    """Build argv for an interactive login shell (allocates a tty, no BatchMode)."""
    return [
        "ssh",
        "-t",
        *ssh_options(batch=False, connect_timeout=connect_timeout, identity=identity),
        destination(host, user),
    ]


def scp_command(
    src: str,
    dst: str,
    *,
    recursive: bool = True,
    identity: str | None = None,
    connect_timeout: int = _DEFAULT_CONNECT_TIMEOUT,
) -> list[str]:
    """Build an scp argv. ``src``/``dst`` are already-formatted local or remote paths."""
    argv = ["scp", *ssh_options(batch=True, connect_timeout=connect_timeout, identity=identity)]
    if recursive:
        argv.append("-r")
    argv += [src, dst]
    return argv


def rsync_command(
    src: str,
    dst: str,
    *,
    identity: str | None = None,
    delete: bool = False,
    connect_timeout: int = _DEFAULT_CONNECT_TIMEOUT,
) -> list[str]:
    """Build an rsync argv that tunnels over ssh with the suite's standard options."""
    transport = "ssh " + " ".join(
        ssh_options(batch=True, connect_timeout=connect_timeout, identity=identity)
    )
    argv = ["rsync", "-az", "--info=progress2"]
    if delete:
        argv.append("--delete")
    argv += ["-e", transport, src, dst]
    return argv


def tunnel_command(
    host: str,
    spec: str,
    *,
    user: str | None = None,
    identity: str | None = None,
    connect_timeout: int = _DEFAULT_CONNECT_TIMEOUT,
) -> list[str]:
    """Build argv for an ``ssh -N -L`` local port-forward."""
    return [
        "ssh",
        "-N",
        "-L",
        spec,
        *ssh_options(batch=True, connect_timeout=connect_timeout, identity=identity),
        destination(host, user),
    ]
