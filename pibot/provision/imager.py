"""Thin wrapper around ``rpi-imager --cli`` and macOS raw-disk handling.

The argv builder is pure; the suite owns the SHA-256 verification value and (on
macOS) unmounting + writing to the raw ``/dev/rdiskN`` node, which the GUI-oriented
CLI does not do for you.
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


def macos_raw_device(node: str) -> str:
    """Map ``/dev/diskN`` to the faster raw ``/dev/rdiskN``; leave others unchanged."""
    if node.startswith("/dev/disk"):
        return node.replace("/dev/disk", "/dev/rdisk", 1)
    return node
