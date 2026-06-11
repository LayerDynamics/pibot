"""Raspberry Pi bootloader EEPROM management, driven over SSH.

Wraps ``rpi-eeprom-update`` and ``rpi-eeprom-config`` on the Pi. Writes (update,
BOOT_ORDER change) are destructive to the bootloader and require ``confirm=True``.
BOOT_ORDER is set non-interactively by reading the current config, replacing the
line, and applying it (``rpi-eeprom-config --apply``).
"""

from __future__ import annotations

import re

from pibot.config import Config
from pibot.connection import commands
from pibot.errors import PibotError, UsageError
from pibot.inventory import Inventory

_BOOT_ORDER_RE = re.compile(r"^0[xX][0-9a-fA-F]+$")


def validate_boot_order(value: str) -> str:
    """Validate a BOOT_ORDER hex value (e.g. NVMe-first ``0xf416``)."""
    if not _BOOT_ORDER_RE.fullmatch(value or ""):
        raise UsageError(f"invalid BOOT_ORDER {value!r}: expected hex like 0xf416")
    return value.lower()


def status(
    target: str,
    *,
    cfg: Config,
    inventory: Inventory,
    user: str | None = None,
    dry_run: bool = False,
) -> int:
    """Show the current bootloader status (``rpi-eeprom-update``)."""
    return commands.run(
        target,
        ["rpi-eeprom-update"],
        cfg=cfg,
        inventory=inventory,
        explicit_user=user,
        dry_run=dry_run,
    )


def show_config(
    target: str,
    *,
    cfg: Config,
    inventory: Inventory,
    user: str | None = None,
    dry_run: bool = False,
) -> int:
    """Print the current bootloader configuration (``rpi-eeprom-config``)."""
    return commands.run(
        target,
        ["rpi-eeprom-config"],
        cfg=cfg,
        inventory=inventory,
        explicit_user=user,
        dry_run=dry_run,
    )


def update(
    target: str,
    *,
    cfg: Config,
    inventory: Inventory,
    user: str | None = None,
    confirm: bool = False,
    dry_run: bool = False,
) -> int:
    """Update the bootloader to the latest (``sudo rpi-eeprom-update -a``)."""
    if not confirm and not dry_run:
        raise PibotError("updating the bootloader is destructive; pass --confirm")
    return commands.run(
        target,
        ["sudo", "rpi-eeprom-update", "-a"],
        cfg=cfg,
        inventory=inventory,
        explicit_user=user,
        dry_run=dry_run,
    )


def _boot_order_script(value: str) -> str:
    return (
        'tmp="$(mktemp)"; rpi-eeprom-config > "$tmp"; '
        f'if grep -q "^BOOT_ORDER=" "$tmp"; then '
        f'sed -i "s/^BOOT_ORDER=.*/BOOT_ORDER={value}/" "$tmp"; '
        f'else echo "BOOT_ORDER={value}" >> "$tmp"; fi; '
        'sudo rpi-eeprom-config --apply "$tmp"'
    )


def set_boot_order(
    target: str,
    value: str,
    *,
    cfg: Config,
    inventory: Inventory,
    user: str | None = None,
    confirm: bool = False,
    dry_run: bool = False,
) -> int:
    """Set the bootloader BOOT_ORDER (e.g. ``0xf416`` = NVMe first)."""
    normalized = validate_boot_order(value)
    if not confirm and not dry_run:
        raise PibotError("changing BOOT_ORDER is destructive; pass --confirm")
    return commands.run(
        target,
        ["bash", "-c", _boot_order_script(normalized)],
        cfg=cfg,
        inventory=inventory,
        explicit_user=user,
        dry_run=dry_run,
    )
