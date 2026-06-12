"""Bind and run the control-plane sidecar on loopback.

The Rust supervisor spawns ``python -m pibot.mc --port 0 --token <t>``; on bind the
process prints ``PORT=<n>`` on stdout so the Rust core can discover the chosen port
(SPEC-3 §3.1 port discovery). Bound strictly to 127.0.0.1 (never a public interface).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

from aiohttp import web

from pibot.mc.app import create_mc_app

# Loopback only — the control plane is never exposed on a routable interface (SPEC-3 §3.7).
HOST = "127.0.0.1"


async def serve(
    *,
    token: str,
    port: int = 0,
    on_bound: Callable[[int], None] | None = None,
) -> None:
    """Serve the control-plane app on ``HOST:port`` until cancelled.

    With ``port=0`` the OS assigns a free port; the bound port is reported via
    ``on_bound`` (tests) and printed as ``PORT=<n>`` (the Rust supervisor).
    """
    app = create_mc_app(token=token)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        site = web.TCPSite(runner, HOST, port)
        await site.start()
        bound = _bound_port(runner, fallback=port)
        if on_bound is not None:
            on_bound(bound)
        print(f"PORT={bound}", flush=True)
        await asyncio.Event().wait()  # run until cancelled
    finally:
        await runner.cleanup()


def _bound_port(runner: web.AppRunner, *, fallback: int) -> int:
    """Read the actually-bound TCP port from the runner's server sockets."""
    for addr in runner.addresses:
        # addr is (host, port[, flowinfo, scopeid]); the port is index 1.
        if isinstance(addr, tuple) and len(addr) >= 2 and isinstance(addr[1], int):
            return addr[1]
    return fallback


def run_blocking(*, token: str, port: int = 0) -> None:
    """Entry point: serve forever, exiting cleanly on cancellation/interrupt."""
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(token=token, port=port))
