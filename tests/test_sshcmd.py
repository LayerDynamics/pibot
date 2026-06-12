"""T1.1 — pure SSH/scp/rsync/tunnel argv construction (no execution)."""

from __future__ import annotations

from pibot.connection import sshcmd


def test_ssh_options_defaults_are_safe_for_automation() -> None:
    opts = sshcmd.ssh_options()
    assert "BatchMode=yes" in opts
    assert "StrictHostKeyChecking=accept-new" in opts
    assert "ConnectTimeout=10" in opts


def test_ssh_options_interactive_drops_batchmode() -> None:
    opts = sshcmd.ssh_options(batch=False)
    assert "BatchMode=yes" not in opts
    # host-key acceptance still set so a first connection is not blocked
    assert "StrictHostKeyChecking=accept-new" in opts


def test_ssh_options_identity_included_only_when_given() -> None:
    assert "-i" not in sshcmd.ssh_options(identity=None)
    opts = sshcmd.ssh_options(identity="/home/me/.ssh/pibot_ed25519")
    assert opts[opts.index("-i") + 1] == "/home/me/.ssh/pibot_ed25519"


def test_destination_with_and_without_user() -> None:
    assert sshcmd.destination("192.168.1.99", "ubuntu") == "ubuntu@192.168.1.99"
    assert sshcmd.destination("pibot.local", None) == "pibot.local"


def test_run_command_appends_shell_quoted_remote_command() -> None:
    argv = sshcmd.run_command("192.168.1.99", ["echo", "a b"], user="ubuntu")
    assert argv[0] == "ssh"
    assert argv[-2] == "ubuntu@192.168.1.99"
    # the remote command is one shell-quoted argument so spaces survive
    assert argv[-1] == "echo 'a b'"


def test_run_command_accepts_string_command() -> None:
    argv = sshcmd.run_command("h", "uptime", user="pi")
    assert argv[-1] == "uptime"


def test_interactive_command_requests_a_tty() -> None:
    argv = sshcmd.interactive_command("h", user="pi")
    assert "-t" in argv
    assert "BatchMode=yes" not in argv
    assert argv[-1] == "pi@h"


def test_scp_command_recursive_and_identity() -> None:
    argv = sshcmd.scp_command("ubuntu@h:/etc/hostname", "/tmp/hostname", identity="/k")
    assert argv[0] == "scp"
    assert "-r" in argv
    assert argv[argv.index("-i") + 1] == "/k"
    assert argv[-2:] == ["ubuntu@h:/etc/hostname", "/tmp/hostname"]


def test_rsync_command_embeds_ssh_transport_and_delete() -> None:
    argv = sshcmd.rsync_command("/src/", "ubuntu@h:/dst/", identity="/k", delete=True)
    assert argv[0] == "rsync"
    assert "--delete" in argv
    e_index = argv.index("-e")
    transport = argv[e_index + 1]
    assert transport.startswith("ssh ")
    assert "BatchMode=yes" in transport
    assert "-i /k" in transport
    assert argv[-2:] == ["/src/", "ubuntu@h:/dst/"]


def test_rsync_command_no_delete_by_default() -> None:
    assert "--delete" not in sshcmd.rsync_command("/a", "h:/b")


def test_tunnel_command_local_forward() -> None:
    argv = sshcmd.tunnel_command("192.168.1.99", "8787:127.0.0.1:8787", user="ubuntu")
    assert argv[0] == "ssh"
    assert "-N" in argv
    assert argv[argv.index("-L") + 1] == "8787:127.0.0.1:8787"
    assert argv[-1] == "ubuntu@192.168.1.99"


def test_remote_destination_formats_user_host_path() -> None:
    assert sshcmd.remote_destination("h", "ubuntu", "/etc/x") == "ubuntu@h:/etc/x"
    assert sshcmd.remote_destination("h", None, "/etc/x") == "h:/etc/x"
