"""Typed error hierarchy for the PiBot Control Suite.

Every user-facing failure raises a :class:`PibotError` (or subclass) carrying the
process ``exit_code`` the CLI should return, so the top-level dispatcher can map
exceptions to exit status without per-command bespoke handling.
"""

from __future__ import annotations


class PibotError(Exception):
    """Base class for all suite errors. Default process exit code is 1."""

    exit_code: int = 1


class UsageError(PibotError):
    """Invalid command-line usage (bad flags/args). Mirrors argparse's code 2."""

    exit_code = 2


class ConfigError(PibotError):
    """The configuration file is missing required values or is malformed."""

    exit_code = 1


class InventoryError(PibotError):
    """A host inventory operation failed (unknown target, bad record, …)."""

    exit_code = 1


class ConnectionError(PibotError):
    """An SSH / network operation against the robot failed."""

    exit_code = 1
