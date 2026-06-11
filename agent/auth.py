"""Bearer-token authentication for the pibotd agent.

The agent binds to loopback by default and is reached from the Mac via ``pibot tunnel``;
loopback peers are trusted. Any non-loopback peer must present ``Authorization: Bearer
<token>`` matching the token file (constant-time compared). ``/healthz`` is the one
public route (liveness).
"""

from __future__ import annotations

import hmac
import ipaddress
import secrets
from pathlib import Path


def load_token(path: str | Path) -> str | None:
    """Read the agent token from ``path``, or return None if it does not exist."""
    p = Path(path)
    if not p.exists():
        return None
    token = p.read_text(encoding="utf-8").strip()
    return token or None


def generate_token(path: str | Path, *, nbytes: int = 32) -> str:
    """Ensure a bearer token exists at ``path`` (mode ``0600``) and return it.

    Idempotent: an existing token is preserved (so the host and the Pi keep matching
    secrets across runs). A freshly written file is created ``0600`` — the secret is
    never world-readable, even briefly.
    """
    p = Path(path)
    existing = load_token(p)
    if existing:
        return existing
    token = secrets.token_urlsafe(nbytes)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Create with 0600 from the start (O_CREAT|O_EXCL would race; open then chmod
    # leaves a window) — open via os.open with the mode, then write.
    import os

    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (token + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    p.chmod(0o600)  # belt and suspenders if umask widened the create mode
    return token


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
