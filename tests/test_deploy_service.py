"""T5.2 — agent service lifecycle: systemd unit, venv provisioning, restart+health, rollback."""

from __future__ import annotations

import pibot.deploy.service as service
from pibot.connection.runner import RunResult


def test_render_unit_has_venv_exec_restart_and_journald() -> None:
    unit = service.render_unit(remote_base="/opt/pibot", venv="/opt/pibot/venv", user="pi")
    assert "ExecStart=/opt/pibot/venv/bin/python -m agent" in unit
    assert "WorkingDirectory=/opt/pibot/current" in unit
    assert "Restart=on-failure" in unit
    assert "StandardOutput=journal" in unit  # logs to journald
    assert "User=pi" in unit
    assert "[Install]" in unit and "WantedBy=multi-user.target" in unit


# ---- T7.4: hardened renderers (app watchdog, hardware watchdog, Nebula) ----


def test_render_unit_default_is_unchanged_simple() -> None:
    unit = service.render_unit(remote_base="/opt/pibot", venv="/opt/pibot/venv")
    assert "Type=simple" in unit
    assert "WatchdogSec" not in unit  # opt-in only


def test_render_unit_app_watchdog_mode() -> None:
    unit = service.render_unit(remote_base="/opt/pibot", venv="/opt/pibot/venv", watchdog_sec=30)
    assert "Type=notify" in unit  # sd_notify-driven
    assert "WatchdogSec=30s" in unit
    assert "Restart=on-watchdog" in unit
    assert "StartLimitBurst=" in unit


def test_render_watchdog_conf_within_hardware_limit() -> None:
    conf = service.render_watchdog_conf()
    assert "[Manager]" in conf
    assert "RuntimeWatchdogSec=14" in conf  # <=15s or it silently disables (research)
    assert "RebootWatchdogSec=" in conf


def test_render_nebula_unit_restart_always_unprivileged() -> None:
    unit = service.render_nebula_unit(config="/etc/nebula/config.yml")
    assert "Restart=always" in unit
    assert "ExecStart=" in unit and "/etc/nebula/config.yml" in unit
    assert "CAP_NET_ADMIN" in unit  # unprivileged: tun device without full root


def test_venv_commands_create_and_install_requirements() -> None:
    cmds = service.venv_commands(remote_base="/opt/pibot", venv="/opt/pibot/venv")
    joined = "\n".join(cmds)
    assert "python3 -m venv /opt/pibot/venv" in joined
    assert "/opt/pibot/venv/bin/pip install" in joined
    assert "-r /opt/pibot/current/deploy/requirements.txt" in joined


def test_systemctl_command_builders() -> None:
    assert service.daemon_reload_command() == "sudo systemctl daemon-reload"
    assert service.enable_command() == "sudo systemctl enable pibotd"
    assert service.restart_command() == "sudo systemctl restart pibotd"


def test_install_unit_command_writes_to_systemd_via_sudo_tee() -> None:
    cmd = service.install_unit_command(remote_base="/opt/pibot", venv="/opt/pibot/venv", user="pi")
    assert "sudo tee /etc/systemd/system/pibotd.service" in cmd
    assert "ExecStart=/opt/pibot/venv/bin/python -m agent" in cmd


def test_health_check_command_curls_local_agent() -> None:
    cmd = service.health_check_command(port=8787)
    assert "curl" in cmd and "127.0.0.1:8787/health" in cmd


def test_previous_release_command_excludes_current() -> None:
    cmd = service.previous_release_command("/opt/pibot")
    assert "readlink" in cmd and "/opt/pibot/current" in cmd
    assert "releases" in cmd


def test_install_runs_full_sequence(monkeypatch) -> None:
    ran: list[str] = []

    def fake_capture(argv, **kw):
        ran.append(" ".join(argv))
        out = '{"ok": true}' if "health" in " ".join(argv) else ""
        return RunResult(0, out, "", 0.01)

    monkeypatch.setattr(service.runner, "run_capture", fake_capture)
    rc = service.install("pi@host", remote_base="/opt/pibot", port=8787)
    assert rc == 0
    blob = "\n".join(ran)
    assert "python3 -m venv" in blob  # venv provisioned
    assert "daemon-reload" in blob and "systemctl restart pibotd" in blob
    assert "health" in blob  # post-restart health gate


def test_install_fails_when_health_check_fails(monkeypatch) -> None:
    monkeypatch.setattr(service.time, "sleep", lambda *_: None)  # don't wait between retries

    def fake_capture(argv, **kw):
        joined = " ".join(argv)
        if "health" in joined:
            return RunResult(7, "", "curl: connection refused", 0.01)  # agent didn't come up
        return RunResult(0, "", "", 0.01)

    monkeypatch.setattr(service.runner, "run_capture", fake_capture)
    rc = service.install("pi@host", remote_base="/opt/pibot", port=8787)
    assert rc != 0  # a failed health gate fails the deploy


def test_rollback_repoints_to_previous_and_restarts(monkeypatch) -> None:
    ran: list[str] = []

    def fake_capture(argv, **kw):
        joined = " ".join(argv)
        ran.append(joined)
        if "readlink" in joined:  # previous-release lookup returns an older release id
            return RunResult(0, "20260610T120000Z\n", "", 0.01)
        out = '{"ok": true}' if "health" in joined else ""
        return RunResult(0, out, "", 0.01)

    monkeypatch.setattr(service.runner, "run_capture", fake_capture)
    rc = service.rollback("pi@host", remote_base="/opt/pibot", port=8787)
    assert rc == 0
    blob = "\n".join(ran)
    assert "20260610T120000Z" in blob  # activated the previous release
    assert "ln -sfn" in blob and "systemctl restart pibotd" in blob


def test_rollback_errors_when_no_previous_release(monkeypatch) -> None:
    def fake_capture(argv, **kw):
        if "readlink" in " ".join(argv):
            return RunResult(0, "\n", "", 0.01)  # nothing older to roll back to
        return RunResult(0, "", "", 0.01)

    monkeypatch.setattr(service.runner, "run_capture", fake_capture)
    rc = service.rollback("pi@host", remote_base="/opt/pibot", port=8787)
    assert rc != 0
