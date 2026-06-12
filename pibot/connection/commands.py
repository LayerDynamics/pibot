"""High-level connection commands: run a remote command, open a shell.

These tie the pure argv builders (:mod:`sshcmd`), the executor (:mod:`runner`),
target resolution (:class:`Inventory`), and user resolution (:mod:`user`) together.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence

from pibot.config import Config
from pibot.connection import runner, sshcmd, user
from pibot.inventory import Inventory


def run(
    target: str,
    command: Sequence[str],
    *,
    cfg: Config,
    inventory: Inventory,
    explicit_user: str | None = None,
    identity: str | None = None,
    timeout: float | None = None,
    as_json: bool = False,
) -> int:
    """Run a remote command on ``target`` and return its exit code."""
    address = inventory.resolve(target)
    login = user.resolve_user(address, cfg, explicit=explicit_user)
    ident = identity or cfg.identity
    argv = sshcmd.run_command(address, list(command), user=login, identity=ident)
    result = runner.run_capture(argv, timeout=timeout)
    if as_json:
        print(
            json.dumps(
                {
                    "host": address,
                    "user": login,
                    "command": list(command),
                    "exit": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "duration": round(result.duration, 3),
                }
            )
        )
    else:
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
    return result.exit_code


def connect(
    target: str,
    *,
    cfg: Config,
    inventory: Inventory,
    explicit_user: str | None = None,
    identity: str | None = None,
) -> int:
    """Open an interactive SSH shell to ``target`` and return its exit code."""
    address = inventory.resolve(target)
    login = user.resolve_user(address, cfg, explicit=explicit_user)
    ident = identity or cfg.identity
    argv = sshcmd.interactive_command(address, user=login, identity=ident)
    return runner.run_interactive(argv)
