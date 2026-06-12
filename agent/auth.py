"""Bearer-token authentication for the pibotd agent.

The agent binds to loopback by default and is reached from the Mac via ``pibot tunnel``;
loopback peers are trusted. Any non-loopback peer must present ``Authorization: Bearer
<token>`` matching the token file (constant-time compared). ``/healthz`` is the one
public route (liveness).
"""

from __future__ import annotations

import hmac
import ipaddress
from pathlib import Path


def load_token(path: str | Path) -> str | None:
    """Read the agent token from ``path``, or return None if it does not exist."""
    p = Path(path)
    if not p.exists():
        return None
    token = p.read_text(encoding="utf-8").strip()
    return token or None


def is_loopback(remote: str | None) -> bool:
    """Whether ``remote`` (a peer IP string) is a loopback address."""
    if not remote:
        return False
    try:
        return ipaddress.ip_address(remote).is_loopback
    except ValueError:
        return False


def token_ok(auth_header: str | None, token: str | None) -> bool:
    """Constant-time check of an ``Authorization: Bearer <token>`` header."""
    if not token or not auth_header or not auth_header.startswith("Bearer "):
        return False
    return hmac.compare_digest(auth_header[len("Bearer ") :], token)
