"""Authorization for the loopback control-plane API (SPEC-3 §3.7).

The sidecar is **loopback-only and token-gated**: a peer must be a loopback address
**and** present the per-launch bearer token. Loopback alone is not enough — other local
processes are loopback too, so the token is the real gate. Reuses ``agent.auth`` rather
than re-implementing the constant-time token check.
"""

from __future__ import annotations

from agent.auth import is_loopback, token_ok


def authorize(remote: str | None, auth_header: str | None, token: str | None) -> int | None:
    """Return an HTTP error status to reject the request, or ``None`` to allow it.

    - non-loopback peer            -> 403 (defence in depth; the socket is loopback-bound)
    - missing/incorrect bearer     -> 401
    - loopback peer + valid token  -> allow
    """
    if not is_loopback(remote):
        return 403
    if not token_ok(auth_header, token):
        return 401
    return None
