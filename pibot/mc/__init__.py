"""PiBot Mission Control host (``pibot.mc``) — the desktop app's control-plane sidecar.

A loopback-only aiohttp service the Tauri webview talks to. It reuses the existing
``pibot`` suite (``AgentClient``, ``config``, ``inventory``, …) and the ``pibotd`` link;
it never re-implements transport, protocol, or safety (SPEC-3 FR-25). Bundled inside the
Tauri app and supervised by the Rust core (SPEC-3 §3.1, A2).
"""

from __future__ import annotations

__version__ = "0.1.0"
