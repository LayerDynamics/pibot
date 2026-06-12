"""Resolve which SSH user to log in as for a given robot.

Precedence: an explicit ``--user`` flag, then the user inferred from the server's
SSH identification banner, then the configured default, then ``pi`` (the historical
Raspberry Pi default) as a last resort. The banner is the same signal
``pifinder`` uses to label hosts, so a robot running Ubuntu Server resolves to
``ubuntu`` and one running Raspberry Pi OS to ``pi`` without configuration.
"""

from __future__ import annotations

from collections.abc import Callable

from pibot.config import Config

# Default SSH banner probe — imported lazily so this module has no hard dependency
# on the discovery backend at import time.
_DEFAULT_BANNER_TIMEOUT = 2.0


def user_from_banner(banner: str) -> str | None:
    """Infer the conventional default user from an SSH identification banner."""
    low = banner.lower()
    if "ubuntu" in low:
        return "ubuntu"
    if "raspbian" in low or "debian" in low:
        return "pi"
    return None


def _probe_banner(address: str) -> str:
    from pibot import discovery

    return discovery.get_pifinder().grab_ssh_banner(address, _DEFAULT_BANNER_TIMEOUT)


def resolve_user(
    address: str,
    cfg: Config,
    *,
    explicit: str | None = None,
    banner_fn: Callable[[str], str] | None = None,
) -> str:
    """Resolve the SSH login user for ``address`` (an IP or hostname)."""
    if explicit:
        return explicit
    probe = banner_fn or _probe_banner
    inferred = user_from_banner(probe(address))
    if inferred:
        return inferred
    if cfg.default_user:
        return cfg.default_user
    return "pi"
