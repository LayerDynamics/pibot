"""Resolve external flashing tools, with actionable errors when they're missing.

On macOS these tools are not always on ``PATH``: ``rpi-imager`` ships as a GUI app
bundle, and ``rpiboot`` is built from source by ``scripts/install-flash-tools.sh``
into a cache dir. ``resolve_tool`` therefore checks ``PATH`` first, then a list of
known per-tool locations.
"""

from __future__ import annotations

import os
from pathlib import Path
from shutil import which

from pibot.errors import PibotError

_HOME = Path.home()

# Locations to check beyond PATH, per tool.
_CANDIDATES: dict[str, list[str]] = {
    "rpi-imager": [
        "/Applications/Raspberry Pi Imager.app/Contents/MacOS/rpi-imager",
    ],
    "rpiboot": [
        str(_HOME / ".cache" / "pibot" / "usbboot" / "rpiboot"),
    ],
}

_INSTALL_HINT: dict[str, str] = {
    "rpi-imager": "install with: brew install --cask raspberry-pi-imager",
    "rpiboot": "install with: scripts/install-flash-tools.sh (builds usbboot from source)",
    "arduino-cli": "install with: brew install arduino-cli",
}


def resolve_tool(name: str) -> str | None:
    """Return the path to ``name`` (PATH first, then known candidates), or None."""
    found = which(name)
    if found:
        return found
    for candidate in _CANDIDATES.get(name, []):
        if os.access(candidate, os.X_OK) and os.path.isfile(candidate):
            return candidate
    return None


def require_tool(name: str) -> str:
    """Return the path to ``name`` or raise a PibotError with an install hint."""
    path = resolve_tool(name)
    if path is None:
        hint = _INSTALL_HINT.get(name, "")
        message = f"required tool {name!r} not found"
        if hint:
            message += f" — {hint}"
        raise PibotError(message)
    return path


# rpiboot's ``-d`` flag needs the real path to the mass-storage gadget boot-files
# directory, NOT a bare name (a bare name fails with "No 'bootcode' files found").
# The directory ships next to the rpiboot binary (source build) or under
# ``<prefix>/share/rpiboot`` (Homebrew / distro packages).
_GADGET_DIR = "mass-storage-gadget64"


def resolve_gadget_dir(rpiboot_binary: str) -> str | None:
    """Return the absolute path to the rpiboot mass-storage gadget dir, or None."""
    bin_path = Path(rpiboot_binary)
    if bin_path.exists():
        bin_path = bin_path.resolve()
    bin_dir = bin_path.parent
    candidates = [
        bin_dir / _GADGET_DIR,  # source build: usbboot/rpiboot + usbboot/mass-storage-gadget64
        bin_dir.parent / "share" / "rpiboot" / _GADGET_DIR,  # Homebrew: bin -> ../share/rpiboot
        _HOME / ".cache" / "pibot" / "usbboot" / _GADGET_DIR,
        Path("/opt/homebrew/share/rpiboot") / _GADGET_DIR,
        Path("/usr/share/rpiboot") / _GADGET_DIR,  # Linux distro package
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return str(candidate)
    return None


def require_gadget_dir(rpiboot_binary: str) -> str:
    """Return the rpiboot mass-storage gadget dir or raise with an install hint."""
    path = resolve_gadget_dir(rpiboot_binary)
    if path is None:
        raise PibotError(
            f"rpiboot mass-storage gadget dir {_GADGET_DIR!r} not found near "
            f"{rpiboot_binary!r} — reinstall with scripts/install-flash-tools.sh"
        )
    return path
