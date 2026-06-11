"""Enable ``python -m pibot`` as an alias for the ``pibot`` console script."""

from __future__ import annotations

import sys

from pibot.cli import main

if __name__ == "__main__":
    sys.exit(main())
