"""``pibot agent`` — manage the pibotd agent on the Pi over SSH (M1 connection layer).

M4 provides the manual/foreground lifecycle (launch ``python -m agent``, check
``/healthz``, tail the log, kill it). The systemd unit + venv provisioning land in M5
(``pibot deploy``); these commands target a Pi where the agent payload is already present.
"""

from __future__ import annotations

from pibot.config import Config
from pibot.connection import commands
from pibot.inventory import Inventory

_LOG = "~/.cache/pibot/pibotd.log"


def _port(cfg: Config) -> int:
    return int(cfg.agent_bind.rsplit(":", 1)[1])


def start(
    target: str,
    *,
    cfg: Config,
    inventory: Inventory,
    user: str | None = None,
    python: str = "python3",
    dry_run: bool = False,
) -> int:
    """Launch pibotd on the Pi (backgrounded, logging to the agent log)."""
    script = (
        f"mkdir -p ~/.cache/pibot && "
        f"nohup {python} -m agent >> {_LOG} 2>&1 & "
        f"echo pibotd-started pid=$!"
    )
    return commands.run(
        target,
        ["bash", "-lc", script],
        cfg=cfg,
        inventory=inventory,
        explicit_user=user,
        dry_run=dry_run,
    )


def stop(
    target: str,
    *,
    cfg: Config,
    inventory: Inventory,
    user: str | None = None,
    dry_run: bool = False,
) -> int:
    """Stop pibotd on the Pi."""
    script = "pkill -f 'python.* -m agent' && echo stopped || echo not-running"
    return commands.run(
        target,
        ["bash", "-lc", script],
        cfg=cfg,
        inventory=inventory,
        explicit_user=user,
        dry_run=dry_run,
    )


def status(target: str, *, cfg: Config, inventory: Inventory, user: str | None = None) -> int:
    """Report whether pibotd is responding to its health probe."""
    script = f"curl -fsS http://127.0.0.1:{_port(cfg)}/healthz && echo || echo DOWN"
    return commands.run(
        target, ["bash", "-lc", script], cfg=cfg, inventory=inventory, explicit_user=user
    )


def logs(
    target: str,
    *,
    cfg: Config,
    inventory: Inventory,
    user: str | None = None,
    lines: int = 50,
) -> int:
    """Tail the pibotd log."""
    script = f"tail -n {int(lines)} {_LOG}"
    return commands.run(
        target, ["bash", "-lc", script], cfg=cfg, inventory=inventory, explicit_user=user
    )
