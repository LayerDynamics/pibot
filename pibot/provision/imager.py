"""Thin wrapper around ``rpi-imager --cli``.

The argv builder is pure; the suite owns the SHA-256 verification value and (on macOS)
unmounting the target disk first. ``rpi-imager --cli`` is given the plain ``/dev/diskN``
node — it matches its removable-drive allowlist by that name and does the raw-device
write itself, so passing ``/dev/rdiskN`` makes it reject the target.
"""

from __future__ import annotations


def imager_argv(
    image: str,
    device: str,
    *,
    binary: str,
    sha256: str | None = None,
    disable_verify: bool = False,
    quiet: bool = True,
) -> list[str]:
    """Build an ``rpi-imager --cli`` argv writing ``image`` to ``device``."""
    argv = [binary, "--cli"]
    if quiet:
        argv.append("--quiet")
    if disable_verify:
        argv.append("--disable-verify")
    if sha256:
        argv += ["--sha256", sha256]
    argv += [image, device]
    return argv
