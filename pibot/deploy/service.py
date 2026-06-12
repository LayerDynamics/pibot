"""Agent service lifecycle on the Pi: systemd unit, venv, restart+health, rollback.

``pibotd`` runs under systemd as ``<venv>/bin/python -m agent`` with
``WorkingDirectory=<base>/current`` — so a deploy that swaps the ``current`` symlink
and restarts the unit picks up the new code, while the venv (shared across releases)
carries the third-party deps. Every install ends with a ``/health`` gate: if the agent
doesn't come up, the deploy fails loudly rather than leaving a dead robot. ``rollback``
repoints ``current`` at the previous release and restarts.
"""

from __future__ import annotations

import time

from pibot.connection import runner, sshcmd
from pibot.deploy import sync
from pibot.logging import get_logger

_log = get_logger("deploy")

SERVICE_NAME = "pibotd"
UNIT_PATH = f"/etc/systemd/system/{SERVICE_NAME}.service"


def render_unit(
    *, remote_base: str, venv: str, user: str = "pi", watchdog_sec: int | None = None
) -> str:
    """Render the systemd unit for pibotd (venv exec, restart-on-failure, journald).

    Passing ``watchdog_sec`` switches the unit to ``Type=notify`` with a systemd
    application watchdog: pibotd must ping ``sd_notify("WATCHDOG=1")`` within the window
    or systemd restarts it (``Restart=on-watchdog``), rate-limited by ``StartLimitBurst``.
    """
    base = remote_base.rstrip("/")
    if watchdog_sec is not None:
        service_type, restart = "notify", "on-watchdog"
        watchdog = f"WatchdogSec={watchdog_sec}s\nStartLimitIntervalSec=60\nStartLimitBurst=5\n"
    else:
        service_type, restart, watchdog = "simple", "on-failure", ""
    return (
        "[Unit]\n"
        "Description=PiBot robot control agent (pibotd)\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        f"Type={service_type}\n"
        f"User={user}\n"
        f"WorkingDirectory={base}/current\n"
        f"ExecStart={venv}/bin/python -m agent\n"
        f"Restart={restart}\n"
        "RestartSec=2\n"
        f"{watchdog}"
        "StandardOutput=journal\n"
        "StandardError=journal\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def render_watchdog_conf(runtime_sec: int = 14, reboot: str = "2min") -> str:
    """A ``/etc/systemd/system.conf.d`` drop-in arming the **hardware** watchdog.

    ``RuntimeWatchdogSec`` MUST be ≤ 15 s or the kernel silently disables it (research /
    systemd #27427); a frozen kernel then reboots after ``RebootWatchdogSec``.
    """
    runtime_sec = min(runtime_sec, 15)
    return (
        "# PiBot: arm the BCM hardware watchdog (a frozen kernel reboots itself).\n"
        "[Manager]\n"
        f"RuntimeWatchdogSec={runtime_sec}\n"
        f"RebootWatchdogSec={reboot}\n"
    )


def render_nebula_unit(
    *, config: str = "/etc/nebula/config.yml", binary: str = "/usr/local/bin/nebula"
) -> str:
    """The Nebula overlay systemd unit — always-restart, unprivileged (no full root)."""
    return (
        "[Unit]\n"
        "Description=Nebula overlay network (PiBot)\n"
        "Wants=basic.target network-online.target\n"
        "After=basic.target network.target network-online.target\n"
        "\n"
        "[Service]\n"
        f"ExecStart={binary} -config {config}\n"
        "ExecReload=/bin/kill -HUP $MAINPID\n"
        "SyslogIdentifier=nebula\n"
        "Restart=always\n"
        "RestartSec=2\n"
        # run unprivileged: the tun device needs only CAP_NET_ADMIN, not full root.
        "AmbientCapabilities=CAP_NET_ADMIN\n"
        "CapabilityBoundingSet=CAP_NET_ADMIN\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def install_unit_command(*, remote_base: str, venv: str, user: str = "pi") -> str:
    """Remote shell that writes the rendered unit to systemd via ``sudo tee``."""
    unit = render_unit(remote_base=remote_base, venv=venv, user=user)
    # heredoc avoids quoting pitfalls across the ssh shell boundary
    return f"sudo tee {UNIT_PATH} >/dev/null <<'PIBOTD_UNIT'\n{unit}PIBOTD_UNIT"


def venv_commands(*, remote_base: str, venv: str) -> list[str]:
    """Commands to create/refresh the Pi-side venv and install runtime requirements."""
    base = remote_base.rstrip("/")
    reqs = f"{base}/current/deploy/requirements.txt"
    return [
        f"python3 -m venv {venv}",
        f"{venv}/bin/pip install -U pip",
        f"{venv}/bin/pip install -r {reqs}",
    ]


def daemon_reload_command() -> str:
    return "sudo systemctl daemon-reload"


def enable_command() -> str:
    return f"sudo systemctl enable {SERVICE_NAME}"


def restart_command() -> str:
    return f"sudo systemctl restart {SERVICE_NAME}"


def health_check_command(*, port: int) -> str:
    """Remote curl against the freshly-restarted agent's ``/health`` endpoint."""
    return f"curl -fsS --max-time 3 http://127.0.0.1:{port}/health"


def previous_release_command(remote_base: str) -> str:
    """Remote shell that prints the newest release that ``current`` does *not* point at."""
    base = remote_base.rstrip("/")
    return (
        f"cur=$(basename $(readlink {base}/current 2>/dev/null)); "
        f'ls -1 {base}/releases 2>/dev/null | sort | grep -vx "$cur" | tail -1'
    )


def _run(destination: str, command: str, *, identity: str | None = None) -> runner.RunResult:
    return runner.run_capture(sshcmd.run_command(destination, command, identity=identity))


def _restart_and_verify(
    destination: str, *, port: int, identity: str | None, attempts: int, delay: float
) -> int:
    """daemon-reload + restart, then poll ``/health`` until it answers or we give up."""
    _run(destination, daemon_reload_command(), identity=identity)
    _run(destination, enable_command(), identity=identity)
    restart = _run(destination, restart_command(), identity=identity)
    if restart.exit_code != 0:
        _log.error("restart failed: %s", restart.stderr.rstrip())
        return restart.exit_code
    for attempt in range(attempts):
        health = _run(destination, health_check_command(port=port), identity=identity)
        if health.exit_code == 0:
            _log.debug("agent healthy after %d attempt(s)", attempt + 1)
            return 0
        time.sleep(delay)
    _log.error("agent did not pass /health after %d attempts", attempts)
    return 1


def install(
    destination: str,
    *,
    remote_base: str = "/opt/pibot",
    venv: str | None = None,
    user: str = "pi",
    port: int = 8787,
    identity: str | None = None,
    health_attempts: int = 10,
    health_delay: float = 0.5,
) -> int:
    """Install/refresh the systemd unit + venv, restart pibotd, and gate on ``/health``."""
    venv = venv or f"{remote_base.rstrip('/')}/venv"
    _run(
        destination,
        install_unit_command(remote_base=remote_base, venv=venv, user=user),
        identity=identity,
    )
    for cmd in venv_commands(remote_base=remote_base, venv=venv):
        result = _run(destination, cmd, identity=identity)
        if result.exit_code != 0:
            _log.error("venv step failed: %s", result.stderr.rstrip())
            return result.exit_code
    return _restart_and_verify(
        destination,
        port=port,
        identity=identity,
        attempts=health_attempts,
        delay=health_delay,
    )


def rollback(
    destination: str,
    *,
    remote_base: str = "/opt/pibot",
    port: int = 8787,
    identity: str | None = None,
    health_attempts: int = 10,
    health_delay: float = 0.5,
) -> int:
    """Repoint ``current`` at the previous release and restart pibotd (with health gate)."""
    prev = _run(destination, previous_release_command(remote_base), identity=identity)
    name = prev.stdout.strip()
    if not name:
        _log.error("no previous release to roll back to under %s/releases", remote_base)
        return 1
    _log.info("rolling back to release %s", name)
    _run(destination, sync.activate_command(remote_base, name), identity=identity)
    return _restart_and_verify(
        destination,
        port=port,
        identity=identity,
        attempts=health_attempts,
        delay=health_delay,
    )
