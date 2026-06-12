"""``pibot deploy`` payload sync — rsync the installable package into a fresh,
timestamped release dir on the Pi, then atomically repoint ``current`` at it.

The deploy is *atomic and reversible*: each push lands in ``<base>/releases/<ts>/``
and only on success do we swap the ``current`` symlink, so a half-synced release
never replaces a working one and the previous release stays on disk for rollback
(see :mod:`pibot.deploy.service`). ``--dry-run`` runs rsync with ``-n`` to compute
the change set and writes nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pibot.connection import runner, sshcmd
from pibot.logging import get_logger

_log = get_logger("deploy")

_DEPLOYIGNORE = Path(__file__).resolve().parents[2] / "deploy" / ".deployignore"


def load_excludes(path: Path | None = None) -> list[str]:
    """Read ``deploy/.deployignore`` into rsync ``--exclude`` patterns (comments stripped)."""
    target = path or _DEPLOYIGNORE
    patterns: list[str] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def build_rsync_argv(
    src_root: str,
    remote: str,
    *,
    excludes: Sequence[str] = (),
    identity: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Build the rsync argv that syncs ``src_root`` into the remote release dir.

    ``-i`` itemizes the changes (parsed by :func:`parse_changes`); ``--delete`` makes
    the release dir an exact mirror of the payload; ``-n`` makes it a no-write dry run.
    """
    transport = "ssh " + " ".join(sshcmd.ssh_options(batch=True, identity=identity))
    argv = ["rsync", "-a", "--delete", "-i"]
    if dry_run:
        argv.append("-n")
    for pattern in excludes:
        argv += ["--exclude", pattern]
    argv += ["-e", transport, src_root, remote]
    return argv


def parse_changes(itemized: str) -> list[str]:
    """Extract content-changed/created/deleted paths from rsync ``-i`` output.

    rsync itemize codes: a leading ``>``/``<`` is a transfer, ``c`` a local change, and
    ``*deleting`` a removal — all real changes. A leading ``.`` is attributes-only (e.g.
    a touched directory) and is *not* reported as a change.
    """
    changed: list[str] = []
    for line in itemized.splitlines():
        line = line.rstrip()
        if not line:
            continue
        code, _, path = line.partition(" ")
        path = path.strip()
        if path and code[:1] in ("<", ">", "c", "*"):
            changed.append(path)
    return changed


def new_release_name(now: datetime | None = None) -> str:
    """A lexically-sortable UTC release id, e.g. ``20260611T200318Z``."""
    stamp = now or datetime.now(UTC)
    return stamp.strftime("%Y%m%dT%H%M%SZ")


def remote_release_dir(base: str, name: str) -> str:
    """Path of release ``name`` under ``base`` (``<base>/releases/<name>``)."""
    return f"{base.rstrip('/')}/releases/{name}"


def mkdir_command(base: str, name: str) -> str:
    """Remote shell to create the release dir (and the releases/ parent)."""
    return f"mkdir -p {remote_release_dir(base, name)}"


def activate_command(base: str, name: str) -> str:
    """Remote shell that atomically repoints ``current`` at release ``name``.

    Writes a temp symlink then renames it over ``current`` so readers never observe a
    missing or half-written link (``mv -T`` is an atomic rename on the same filesystem).
    """
    base = base.rstrip("/")
    tmp = f"{base}/.current.tmp"
    return f"ln -sfn {base}/releases/{name} {tmp} && mv -T {tmp} {base}/current"


@dataclass
class DeployResult:
    """Outcome of a payload sync."""

    release: str
    changed: list[str]
    activated: bool


def deploy(
    destination: str,
    *,
    src_root: str,
    remote_base: str = "/opt/pibot",
    identity: str | None = None,
    dry_run: bool = False,
    name: str | None = None,
) -> DeployResult:
    """Sync the payload to a new release on ``destination`` (``user@host``) and activate it.

    Returns the release path and the change set. A dry run computes the diff via rsync
    ``-n`` and never creates the dir or swaps the ``current`` symlink.
    """
    release = name or new_release_name()
    remote_dir = remote_release_dir(remote_base, release)
    if not dry_run:
        runner.run_capture(sshcmd.run_command(destination, mkdir_command(remote_base, release)))
    argv = build_rsync_argv(
        src_root,
        f"{destination}:{remote_dir}/",
        excludes=load_excludes(),
        identity=identity,
        dry_run=dry_run,
    )
    result = runner.run_capture(argv)
    changed = parse_changes(result.stdout)
    if result.stdout:
        _log.debug("rsync itemized %d change(s)", len(changed))
    activated = False
    if not dry_run:
        runner.run_capture(
            sshcmd.run_command(
                destination, activate_command(remote_base, release), identity=identity
            )
        )
        activated = True
    return DeployResult(release=remote_dir, changed=changed, activated=activated)
