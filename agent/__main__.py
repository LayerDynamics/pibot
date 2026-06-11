"""``python -m agent`` -> run the pibotd service."""

from __future__ import annotations

import sys

from agent.pibotd import main

if __name__ == "__main__":
    sys.exit(main())
