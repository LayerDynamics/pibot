"""Prove-the-pipe latency probe (SPEC-2 / M7 T7.5).

Measures round-trip latency of the openpi policy websocket — the cheap feasibility check
before any robot-specific code. The timing/stat logic is pure and unit-tested against a
fake policy; the real :class:`WebsocketClientPolicy` and the random observation are built
lazily (``pibot[ml]``) and only on a live run.

    python tools/pipe_check.py --host 192.168.100.1 --port 8000 --rounds 50
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any


def _shape(actions: Any) -> tuple[int, ...]:
    """Dimensions of an action chunk — works for numpy arrays and nested lists."""
    if hasattr(actions, "shape"):
        return tuple(int(d) for d in actions.shape)
    dims: list[int] = []
    cur = actions
    while isinstance(cur, (list, tuple)):
        dims.append(len(cur))
        cur = cur[0] if cur else None
    return tuple(dims)


def measure(
    policy: Any,
    obs: dict[str, Any],
    *,
    rounds: int = 20,
    clock: Callable[[], float] = time.perf_counter,
) -> dict[str, Any]:
    """Run ``rounds`` ``policy.infer(obs)`` round-trips; return latency stats + chunk shape."""
    latencies: list[float] = []
    shape: tuple[int, ...] = ()
    for _ in range(rounds):
        start = clock()
        reply = policy.infer(obs)
        latencies.append((clock() - start) * 1000.0)
        shape = _shape(reply["actions"])
    latencies.sort()
    n = len(latencies)
    median = latencies[n // 2] if n % 2 else (latencies[n // 2 - 1] + latencies[n // 2]) / 2
    p95 = latencies[min(n - 1, int(round(0.95 * (n - 1))))]
    return {
        "rounds": rounds,
        "min_ms": latencies[0],
        "median_ms": median,
        "p95_ms": p95,
        "chunk_shape": shape,
    }


def _build_policy(
    *, host: str, port: int, api_key: str | None = None
) -> Any:  # pragma: no cover - live network
    from openpi_client.websocket_client_policy import WebsocketClientPolicy

    return WebsocketClientPolicy(host=host, port=port, api_key=api_key)


def _random_obs() -> dict[str, Any]:  # pragma: no cover - needs numpy/openpi (live run only)
    import numpy as np

    return {
        "image": {"base_0_rgb": np.zeros((224, 224, 3), dtype=np.uint8)},
        "state": [0.0] * 8,
        "prompt": "pipe check",
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="pipe_check", description="openpi websocket latency probe")
    ap.add_argument("--host", required=True, help="policy server host/IP (the Mac's Nebula IP)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--api-key", dest="api_key", default=None)
    args = ap.parse_args(argv)

    try:
        policy = _build_policy(host=args.host, port=args.port, api_key=args.api_key)
    except Exception as exc:  # noqa: BLE001 - any connect failure is a non-zero exit
        print(f"pipe_check: cannot reach {args.host}:{args.port}: {exc}")
        return 2

    stats = measure(policy, _random_obs(), rounds=args.rounds)
    print(
        f"pipe_check {args.host}:{args.port} rounds={stats['rounds']} "
        f"min={stats['min_ms']:.1f}ms median={stats['median_ms']:.1f}ms "
        f"p95={stats['p95_ms']:.1f}ms chunk={stats['chunk_shape']}"
    )
    return 0
