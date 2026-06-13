"""``python -m pibot.mc`` — launch the control-plane sidecar.

Args (or env): ``--port`` (0 = OS-assigned), ``--token`` / ``PIBOT_MC_TOKEN``. The Rust
core supervises this process and reads ``PORT=<n>`` from stdout to learn the bound port.
"""

from __future__ import annotations

import argparse
import os

from pibot.mc.server import run_blocking


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pibot.mc", description="PiBot Mission Control sidecar")
    parser.add_argument("--port", type=int, default=0, help="loopback port (0 = OS-assigned)")
    parser.add_argument(
        "--token",
        default=None,
        help="per-launch bearer token (falls back to $PIBOT_MC_TOKEN)",
    )
    args = parser.parse_args(argv)
    token = args.token if args.token is not None else os.environ.get("PIBOT_MC_TOKEN", "")
    run_blocking(token=token, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
