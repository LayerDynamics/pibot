"""Typed envelopes for the local control-plane API (SPEC-3 §3.4, typed-first).

These mirror the TypeScript interfaces in ``app/src/lib/api/types.ts`` — keep them in
lockstep so the webview and the sidecar share one contract.
"""

from __future__ import annotations

from typing import TypedDict


class HealthOut(TypedDict):
    ok: bool
    version: str
    connected: bool
    robot: str | None


class ConnectIn(TypedDict):
    robot: str
