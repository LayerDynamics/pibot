"""SSH local port-forward tunnels (e.g. to reach the on-Pi agent or a camera).

A spec is ``LPORT:HOST:RPORT`` or the shorthand ``LPORT:RPORT`` (host defaults to
the robot's loopback), validated before it is handed to ``ssh -L`` so a typo fails
loudly instead of forwarding to the wrong place.
"""

from __future__ import annotations

from pibot.config import Config
from pibot.connection import runner, sshcmd, user
from pibot.errors import UsageError
from pibot.inventory import Inventory


def _is_port(value: str) -> bool:
    return value.isdigit() and 0 < int(value) <= 65535


def parse_spec(spec: str) -> str:
    """Validate and normalize a forward spec to ``LPORT:HOST:RPORT``."""
    parts = spec.split(":")
    if len(parts) == 2:
        lport, rport = parts
        host = "127.0.0.1"
    elif len(parts) == 3:
        lport, host, rport = parts
    else:
        raise UsageError(f"malformed tunnel spec {spec!r}: expected LPORT:HOST:RPORT")
    if not _is_port(lport) or not _is_port(rport):
        raise UsageError(f"malformed tunnel spec {spec!r}: ports must be 1-65535")
    if not host:
        raise UsageError(f"malformed tunnel spec {spec!r}: empty host")
    return f"{lport}:{host}:{rport}"


def open_tunnel(
    target: str,
    spec: str,
    *,
    cfg: Config,
    inventory: Inventory,
    explicit_user: str | None = None,
    identity: str | None = None,
) -> int:
    """Open a blocking local port-forward to ``target``. Returns ssh's exit code."""
    normalized = parse_spec(spec)
    address = inventory.resolve(target)
    login = user.resolve_user(address, cfg, explicit=explicit_user)
    argv = sshcmd.tunnel_command(address, normalized, user=login, identity=identity or cfg.identity)
    return runner.run_interactive(argv)
