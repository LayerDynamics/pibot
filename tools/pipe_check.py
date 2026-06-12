#!/usr/bin/env python3
"""CLI entry for the prove-the-pipe latency probe — see pibot.ml.pipe_check.

python tools/pipe_check.py --host <policy-host> --port 8000 --rounds 50
"""

from pibot.ml.pipe_check import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
