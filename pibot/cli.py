"""Command-line dispatch for the PiBot Control Suite.

M0 wires up ``discover`` and ``inventory``; later milestones register their own
subcommands here (connection, flashing, control, telemetry). Global flags
(``--json``/``--verbose``/``--log-json``/``--timeout``) are accepted both before and
after the subcommand via a shared parent parser using ``SUPPRESS`` defaults so neither
parse position clobbers the other.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from ipaddress import AddressValueError, IPv4Address
from pathlib import Path

from pibot import agent_ctl, discovery
from pibot import monitor as monitor_mod
from pibot.config import Config, load_config
from pibot.connection import commands, keys, sshcmd, transfer, tunnel, user
from pibot.control import oneshot
from pibot.control.sequence import load_sequence
from pibot.deploy import service as deploy_service
from pibot.deploy import sync as deploy_sync
from pibot.errors import PibotError, UsageError
from pibot.inventory import Inventory, InventoryRecord
from pibot.logging import configure_logging, get_logger
from pibot.provision import clone, eeprom, firmware, flash

_log = get_logger("cli")


def _context() -> tuple[Config, Inventory]:
    """Load configuration and inventory for a command invocation."""
    return load_config(), Inventory.load()


def _global_flags() -> argparse.ArgumentParser:
    g = argparse.ArgumentParser(add_help=False)
    g.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="emit machine-readable JSON"
    )
    g.add_argument(
        "--verbose", action="store_true", default=argparse.SUPPRESS, help="enable debug logging"
    )
    g.add_argument(
        "--log-json",
        action="store_true",
        default=argparse.SUPPRESS,
        dest="log_json",
        help="emit logs as JSON",
    )
    g.add_argument(
        "--timeout", type=float, default=argparse.SUPPRESS, help="per-operation timeout in seconds"
    )
    return g


def _target_flags() -> argparse.ArgumentParser:
    t = argparse.ArgumentParser(add_help=False)
    t.add_argument("--user", default=argparse.SUPPRESS, help="SSH user (default: from banner)")
    t.add_argument("--identity", default=argparse.SUPPRESS, help="SSH private key path")
    return t


def _add_dry_run(parser: argparse.ArgumentParser) -> None:
    """Attach the standard ``--dry-run`` flag to a state-changing subcommand."""
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        default=argparse.SUPPRESS,
        help="show what would happen, change nothing",
    )


def build_parser() -> argparse.ArgumentParser:
    g = _global_flags()
    parser = argparse.ArgumentParser(
        prog="pibot",
        description="PiBot Control Suite — discover, control, and provision the robot.",
        parents=[g],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover", parents=[g], help="scan the network for the robot")
    p_disc.add_argument("--cidr", help="network to scan (default: auto-detect every subnet)")
    p_disc.add_argument(
        "--all",
        action="store_true",
        dest="all_hosts",
        default=argparse.SUPPRESS,
        help="detail every host, not just Pis",
    )
    p_disc.set_defaults(func=cmd_discover)

    p_inv = sub.add_parser("inventory", parents=[g], help="manage known robots")
    inv_sub = p_inv.add_subparsers(dest="action", required=True)

    p_list = inv_sub.add_parser("list", parents=[g], help="list known robots")
    p_list.set_defaults(func=cmd_inventory_list)

    p_add = inv_sub.add_parser("add", parents=[g], help="add or update a robot")
    p_add.add_argument("alias")
    p_add.add_argument("address", help="IPv4 address or hostname")
    p_add.add_argument("--user", help="default SSH user for this robot")
    p_add.set_defaults(func=cmd_inventory_add)

    p_rm = inv_sub.add_parser("rm", parents=[g], help="remove a robot")
    p_rm.add_argument("alias")
    p_rm.set_defaults(func=cmd_inventory_rm)

    p_alias = inv_sub.add_parser("alias", parents=[g], help="rename a robot")
    p_alias.add_argument("old")
    p_alias.add_argument("new")
    p_alias.set_defaults(func=cmd_inventory_alias)

    t = _target_flags()

    p_run = sub.add_parser("run", parents=[g, t], help="run a remote command")
    p_run.add_argument("target")
    p_run.add_argument("command", nargs=argparse.REMAINDER, help="-- <command...>")
    p_run.set_defaults(func=cmd_run)

    p_connect = sub.add_parser("connect", parents=[g, t], help="open an interactive shell")
    p_connect.add_argument("target")
    p_connect.set_defaults(func=cmd_connect)

    p_push = sub.add_parser("push", parents=[g, t], help="copy a local path to the robot")
    p_push.add_argument("target")
    p_push.add_argument("src")
    p_push.add_argument("dst")
    p_push.add_argument(
        "--verify",
        action="store_true",
        default=argparse.SUPPRESS,
        help="verify the transfer by sha256 (files only)",
    )
    p_push.add_argument(
        "--no-rsync",
        action="store_true",
        dest="no_rsync",
        default=argparse.SUPPRESS,
        help="force scp instead of rsync",
    )
    _add_dry_run(p_push)
    p_push.set_defaults(func=cmd_push)

    p_pull = sub.add_parser("pull", parents=[g, t], help="copy a path from the robot")
    p_pull.add_argument("target")
    p_pull.add_argument("src")
    p_pull.add_argument("dst")
    p_pull.add_argument(
        "--verify",
        action="store_true",
        default=argparse.SUPPRESS,
        help="verify the transfer by sha256 (files only)",
    )
    p_pull.add_argument(
        "--no-rsync",
        action="store_true",
        dest="no_rsync",
        default=argparse.SUPPRESS,
        help="force scp instead of rsync",
    )
    _add_dry_run(p_pull)
    p_pull.set_defaults(func=cmd_pull)

    p_keys = sub.add_parser("keys", parents=[g], help="manage SSH keys")
    keys_sub = p_keys.add_subparsers(dest="action", required=True)
    p_keys_install = keys_sub.add_parser(
        "install", parents=[g, t], help="install the pibot key on a robot"
    )
    p_keys_install.add_argument("target")
    p_keys_install.add_argument(
        "--key-path",
        dest="key_path",
        default=argparse.SUPPRESS,
        help="private key path (default: ~/.ssh/pibot_ed25519)",
    )
    _add_dry_run(p_keys_install)
    p_keys_install.set_defaults(func=cmd_keys_install)

    p_tunnel = sub.add_parser("tunnel", parents=[g, t], help="open an SSH port-forward")
    p_tunnel.add_argument("target")
    p_tunnel.add_argument("spec", help="LPORT:HOST:RPORT or LPORT:RPORT")
    p_tunnel.set_defaults(func=cmd_tunnel)

    # ---- provisioning & flashing ----
    p_flash = sub.add_parser("flash", parents=[g], help="write an OS image to the Pi")
    flash_dest = p_flash.add_mutually_exclusive_group(required=True)
    flash_dest.add_argument(
        "--target",
        choices=["nvme", "sd"],
        help="reflash the Pi's onboard drive via rpiboot (hold power button)",
    )
    flash_dest.add_argument("--device", help="write to a removable device node, e.g. /dev/disk4")
    p_flash.add_argument("--image", required=True, help="image file or URL")
    p_flash.add_argument("--sha256", help="expected image SHA-256")
    p_flash.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        default=argparse.SUPPRESS,
        help="print the commands, write nothing",
    )
    p_flash.add_argument(
        "--confirm",
        action="store_true",
        default=argparse.SUPPRESS,
        help="required to actually write",
    )
    p_flash.add_argument("--hostname", help="hostname for the flashed OS (default: pibot)")
    p_flash.add_argument("--username", help="first user (default: ubuntu for --os ubuntu, else pi)")
    p_flash.add_argument(
        "--os",
        choices=["ubuntu", "rpi-os"],
        dest="os_flavor",
        help="OS flavor: cloud-init (ubuntu) vs custom.toml (rpi-os)",
    )
    p_flash.add_argument(
        "--authorized-key",
        action="append",
        dest="authorized_keys",
        default=argparse.SUPPRESS,
        help="SSH public key to authorize on first boot (repeatable)",
    )
    p_flash.add_argument(
        "--authorized-key-file",
        dest="key_file",
        default=argparse.SUPPRESS,
        help="read a public key from a file, e.g. ~/.ssh/id_ed25519.pub",
    )
    p_flash.set_defaults(func=cmd_flash)

    p_eeprom = sub.add_parser("eeprom", parents=[g, t], help="manage the Pi bootloader EEPROM")
    p_eeprom.add_argument("target")
    p_eeprom.add_argument("action", choices=["status", "update", "config", "boot-order"])
    p_eeprom.add_argument("value", nargs="?", help="BOOT_ORDER value for boot-order, e.g. 0xf416")
    p_eeprom.add_argument(
        "--confirm",
        action="store_true",
        default=argparse.SUPPRESS,
        help="required for update / boot-order",
    )
    _add_dry_run(p_eeprom)
    p_eeprom.set_defaults(func=cmd_eeprom)

    p_prov = sub.add_parser("provision", parents=[g], help="clone/restore the Pi NVMe")
    prov_sub = p_prov.add_subparsers(dest="action", required=True)
    p_clone = prov_sub.add_parser("clone", parents=[g, t], help="back up the Pi NVMe to an image")
    p_clone.add_argument("target")
    p_clone.add_argument("--to", required=True, dest="to_file", help="output image (.img.gz)")
    p_clone.add_argument("--device", default="/dev/nvme0n1", help="source device on the Pi")
    p_clone.add_argument("--shrink", action="store_true", default=argparse.SUPPRESS)
    _add_dry_run(p_clone)
    p_clone.set_defaults(func=cmd_provision_clone)
    p_restore = prov_sub.add_parser("restore", parents=[g, t], help="restore an image to the Pi")
    p_restore.add_argument("target")
    p_restore.add_argument("--from", required=True, dest="from_file", help="image to restore")
    p_restore.add_argument("--device", default="/dev/nvme0n1", help="target device on the Pi")
    p_restore.add_argument("--confirm", action="store_true", default=argparse.SUPPRESS)
    _add_dry_run(p_restore)
    p_restore.set_defaults(func=cmd_provision_restore)

    p_fw = sub.add_parser("firmware", parents=[g], help="build/flash Arduino firmware")
    fw_sub = p_fw.add_subparsers(dest="action", required=True)
    p_fw_build = fw_sub.add_parser("build", parents=[g], help="compile a sketch")
    p_fw_build.add_argument("sketch")
    p_fw_build.add_argument("--fqbn", required=True, help="e.g. arduino:avr:uno")
    p_fw_build.set_defaults(func=cmd_firmware_build)
    p_fw_flash = fw_sub.add_parser("flash", parents=[g], help="upload a sketch (USB or OTA)")
    p_fw_flash.add_argument("sketch")
    p_fw_flash.add_argument("--fqbn", required=True, help="e.g. arduino:avr:uno")
    p_fw_flash.add_argument("--port", help="USB serial port, e.g. /dev/ttyACM0")
    p_fw_flash.add_argument(
        "--ota", dest="ota_host", help="flash over WiFi (OTA) to this host/IP instead of USB"
    )
    p_fw_flash.add_argument("--ota-port", dest="ota_port", type=int, default=3232)
    p_fw_flash.add_argument("--ota-pass", dest="ota_pass", default="", help="OTA password if set")
    _add_dry_run(p_fw_flash)
    p_fw_flash.set_defaults(func=cmd_firmware_flash)

    # ---- control ----
    _transports = ["serial", "tcp", "responder", "loopback"]
    p_cmd = sub.add_parser("cmd", parents=[g], help="send one command to the robot")
    p_cmd.add_argument("target")
    p_cmd.add_argument("command", help="drive|servo|motor|stop|estop|ping|set")
    p_cmd.add_argument("args", nargs="*", help="command arguments, e.g. 0.5 0.0")
    p_cmd.add_argument(
        "--transport",
        dest="transport_override",
        choices=_transports,
        default=argparse.SUPPRESS,
        help="override the configured transport",
    )
    _add_dry_run(p_cmd)
    p_cmd.set_defaults(func=cmd_cmd)

    p_estop = sub.add_parser("estop", parents=[g], help="emergency-stop the robot")
    p_estop.add_argument("target")
    p_estop.add_argument(
        "--transport", dest="transport_override", choices=_transports, default=argparse.SUPPRESS
    )
    _add_dry_run(p_estop)
    p_estop.set_defaults(func=cmd_estop)

    # ---- agent / teleop / telemetry ----
    p_teleop = sub.add_parser("teleop", parents=[g, t], help="keyboard-drive the robot")
    p_teleop.add_argument("target")
    p_teleop.add_argument("--rate", type=float, default=argparse.SUPPRESS, help="send rate Hz")
    p_teleop.set_defaults(func=cmd_teleop)

    p_monitor = sub.add_parser("monitor", parents=[g], help="live robot + Pi telemetry")
    p_monitor.add_argument("target")
    p_monitor.add_argument(
        "--once", action="store_true", default=argparse.SUPPRESS, help="one snapshot then exit"
    )
    p_monitor.add_argument("--csv", action="store_true", dest="as_csv", default=argparse.SUPPRESS)
    p_monitor.add_argument("--interval", type=float, default=argparse.SUPPRESS, help="poll seconds")
    p_monitor.set_defaults(func=cmd_monitor)

    p_agent = sub.add_parser("agent", parents=[g], help="manage the pibotd agent on the Pi")
    agent_sub = p_agent.add_subparsers(dest="action", required=True)
    for action in ("status", "start", "stop", "logs"):
        ap = agent_sub.add_parser(action, parents=[g, t], help=f"{action} pibotd")
        ap.add_argument("target")
        if action == "logs":
            ap.add_argument("--lines", type=int, default=50)
        if action in ("start", "stop"):
            _add_dry_run(ap)
        ap.set_defaults(func=cmd_agent, agent_action=action)
    p_agent_token = agent_sub.add_parser(
        "token", parents=[g], help="generate/show the local agent bearer token"
    )
    p_agent_token.set_defaults(func=cmd_agent_token)

    # ---- deploy / play ----
    p_deploy = sub.add_parser("deploy", parents=[g, t], help="deploy/restart pibotd on the Pi")
    p_deploy.add_argument("target")
    p_deploy.add_argument("--base", default=argparse.SUPPRESS, help="remote install base dir")
    p_deploy.add_argument("--src", default=argparse.SUPPRESS, help="payload root (default: repo)")
    p_deploy.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        default=argparse.SUPPRESS,
        help="compute the change set, write nothing",
    )
    p_deploy.add_argument(
        "--rollback",
        action="store_true",
        default=argparse.SUPPRESS,
        help="restore the previous release and restart",
    )
    p_deploy.set_defaults(func=cmd_deploy)

    p_play = sub.add_parser("play", parents=[g, t], help="run a scripted motion sequence")
    p_play.add_argument("target")
    p_play.add_argument("sequence", help="motion sequence file (.yaml/.json)")
    p_play.add_argument("--rate", type=float, default=argparse.SUPPRESS, help="keepalive Hz")
    _add_dry_run(p_play)
    p_play.set_defaults(func=cmd_play)

    # ---- autonomy (VLA policy) ----
    p_auto = sub.add_parser("autonomy", parents=[g, t], help="run the VLA autonomy loop")
    p_auto.add_argument("target")
    p_auto.add_argument(
        "--open-loop",
        action="store_true",
        dest="open_loop",
        default=argparse.SUPPRESS,
        help="stream observations + log actions, NO actuation (bring-up gate)",
    )
    p_auto.add_argument("--prompt", default=argparse.SUPPRESS, help="task prompt for the policy")
    p_auto.set_defaults(func=cmd_autonomy)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(getattr(args, "verbose", False), getattr(args, "log_json", False))
    try:
        result: int = args.func(args)
        return result
    except PibotError as exc:
        _log.error("%s", exc)
        return exc.exit_code


# ---- discover ------------------------------------------------------------


def cmd_discover(args: argparse.Namespace) -> int:
    cfg = load_config()
    timeout = getattr(args, "timeout", None) or cfg.scan_timeout
    results = discovery.scan(cidr=getattr(args, "cidr", None), timeout=timeout)

    inventory = Inventory.load()
    for record in discovery.discovered_records(results):
        inventory.add(record)
    inventory.save()

    if getattr(args, "json", False):
        print(json.dumps(discovery.scan_to_json(results), indent=2))
    else:
        pf = discovery.get_pifinder()
        show_all = getattr(args, "all_hosts", False)
        for label, hosts in results:
            pf.render(hosts, show_all, False, label)
    return 0


# ---- inventory -----------------------------------------------------------


def cmd_inventory_list(args: argparse.Namespace) -> int:
    records = Inventory.load().list()
    if getattr(args, "json", False):
        print(json.dumps({"hosts": [asdict(r) for r in records]}, indent=2))
        return 0
    if not records:
        print("(inventory empty)")
        return 0
    width = max(len(r.alias) for r in records)
    for rec in records:
        flag = "PI" if rec.pi else "  "
        print(f"{rec.alias.ljust(width)}  {flag}  {rec.address or '-'}  {rec.hostname}")
    return 0


def cmd_inventory_add(args: argparse.Namespace) -> int:
    record = InventoryRecord(alias=args.alias, user=getattr(args, "user", None))
    if _is_ipv4(args.address):
        record.ip = args.address
    else:
        record.hostname = args.address
    inventory = Inventory.load()
    inventory.add(record)
    inventory.save()
    print(f"added {args.alias} -> {args.address}")
    return 0


def cmd_inventory_rm(args: argparse.Namespace) -> int:
    inventory = Inventory.load()
    inventory.remove(args.alias)
    inventory.save()
    print(f"removed {args.alias}")
    return 0


def cmd_inventory_alias(args: argparse.Namespace) -> int:
    inventory = Inventory.load()
    inventory.set_alias(args.old, args.new)
    inventory.save()
    print(f"renamed {args.old} -> {args.new}")
    return 0


def _is_ipv4(value: str) -> bool:
    try:
        IPv4Address(value)
        return True
    except AddressValueError:
        return False


# ---- connection ----------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise UsageError("no command given; use: pibot run <target> -- <command...>")
    return commands.run(
        args.target,
        command,
        cfg=cfg,
        inventory=inv,
        explicit_user=getattr(args, "user", None),
        identity=getattr(args, "identity", None),
        timeout=getattr(args, "timeout", None),
        as_json=getattr(args, "json", False),
    )


def cmd_connect(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    return commands.connect(
        args.target,
        cfg=cfg,
        inventory=inv,
        explicit_user=getattr(args, "user", None),
        identity=getattr(args, "identity", None),
    )


def _rsync_override(args: argparse.Namespace) -> bool | None:
    return False if getattr(args, "no_rsync", False) else None


def cmd_push(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    return transfer.push(
        args.target,
        args.src,
        args.dst,
        cfg=cfg,
        inventory=inv,
        explicit_user=getattr(args, "user", None),
        identity=getattr(args, "identity", None),
        verify=getattr(args, "verify", False),
        rsync_available=_rsync_override(args),
        dry_run=getattr(args, "dry_run", False),
    )


def cmd_pull(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    return transfer.pull(
        args.target,
        args.src,
        args.dst,
        cfg=cfg,
        inventory=inv,
        explicit_user=getattr(args, "user", None),
        identity=getattr(args, "identity", None),
        verify=getattr(args, "verify", False),
        rsync_available=_rsync_override(args),
        dry_run=getattr(args, "dry_run", False),
    )


def cmd_keys_install(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    key_path = Path(args.key_path) if getattr(args, "key_path", None) else None
    return keys.install_key(
        args.target,
        cfg=cfg,
        inventory=inv,
        key_path=key_path,
        explicit_user=getattr(args, "user", None),
        identity=getattr(args, "identity", None),
        dry_run=getattr(args, "dry_run", False),
    )


def cmd_tunnel(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    return tunnel.open_tunnel(
        args.target,
        args.spec,
        cfg=cfg,
        inventory=inv,
        explicit_user=getattr(args, "user", None),
        identity=getattr(args, "identity", None),
    )


# ---- provisioning & flashing ---------------------------------------------


def _build_first_boot(args: argparse.Namespace) -> flash.FirstBootSpec | None:
    keys = list(getattr(args, "authorized_keys", None) or [])
    key_file = getattr(args, "key_file", None)
    if key_file:
        keys.append(Path(key_file).expanduser().read_text(encoding="utf-8").strip())
    hostname = getattr(args, "hostname", None)
    username = getattr(args, "username", None)
    flavor = getattr(args, "os_flavor", None)
    if not (keys or hostname or username or flavor):
        return None
    if not keys:
        raise UsageError(
            "first-boot config requested but no key; pass --authorized-key/--authorized-key-file"
        )
    default_user = "ubuntu" if flavor == "ubuntu" else "pi"
    return flash.FirstBootSpec(
        hostname=hostname or "pibot",
        username=username or default_user,
        ssh_authorized_keys=keys,
        flavor=flavor,
    )


def cmd_flash(args: argparse.Namespace) -> int:
    dry_run = getattr(args, "dry_run", False)
    if not dry_run and not getattr(args, "confirm", False):
        raise UsageError("flashing is destructive; pass --confirm (or --dry-run to preview)")
    sha256 = getattr(args, "sha256", None)
    first_boot = _build_first_boot(args)
    if getattr(args, "device", None):
        return flash.flash_to_device(
            args.image, args.device, sha256=sha256, dry_run=dry_run, first_boot=first_boot
        )
    return flash.flash_via_rpiboot(
        args.image, sha256=sha256, dry_run=dry_run, first_boot=first_boot
    )


def cmd_eeprom(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    user_arg = getattr(args, "user", None)
    confirm = getattr(args, "confirm", False)
    dry_run = getattr(args, "dry_run", False)
    if args.action == "status":
        return eeprom.status(args.target, cfg=cfg, inventory=inv, user=user_arg, dry_run=dry_run)
    if args.action == "config":
        return eeprom.show_config(
            args.target, cfg=cfg, inventory=inv, user=user_arg, dry_run=dry_run
        )
    if args.action == "update":
        return eeprom.update(
            args.target, cfg=cfg, inventory=inv, user=user_arg, confirm=confirm, dry_run=dry_run
        )
    if not args.value:
        raise UsageError("boot-order requires a value, e.g. 0xf416")
    return eeprom.set_boot_order(
        args.target,
        args.value,
        cfg=cfg,
        inventory=inv,
        user=user_arg,
        confirm=confirm,
        dry_run=dry_run,
    )


def cmd_provision_clone(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    return clone.clone(
        args.target,
        args.to_file,
        cfg=cfg,
        inventory=inv,
        user=getattr(args, "user", None),
        device=args.device,
        shrink=getattr(args, "shrink", False),
        dry_run=getattr(args, "dry_run", False),
    )


def cmd_provision_restore(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    return clone.restore(
        args.target,
        args.from_file,
        cfg=cfg,
        inventory=inv,
        user=getattr(args, "user", None),
        device=args.device,
        confirm=getattr(args, "confirm", False),
        dry_run=getattr(args, "dry_run", False),
    )


def cmd_firmware_build(args: argparse.Namespace) -> int:
    return firmware.build(args.sketch, fqbn=args.fqbn)


def cmd_firmware_flash(args: argparse.Namespace) -> int:
    dry_run = getattr(args, "dry_run", False)
    ota_host = getattr(args, "ota_host", None)
    if ota_host:
        return firmware.flash_ota(
            args.sketch,
            fqbn=args.fqbn,
            host=ota_host,
            port=getattr(args, "ota_port", 3232),
            password=getattr(args, "ota_pass", ""),
            dry_run=dry_run,
        )
    if not getattr(args, "port", None):
        raise UsageError("firmware flash needs --port (USB) or --ota <host> (wireless)")
    return firmware.flash(args.sketch, fqbn=args.fqbn, port=args.port, dry_run=dry_run)


# ---- control -------------------------------------------------------------


def _control_context(args: argparse.Namespace) -> tuple[Config, Inventory]:
    cfg, inv = _context()
    override = getattr(args, "transport_override", None)
    if override:
        cfg.transport = override
    return cfg, inv


def cmd_cmd(args: argparse.Namespace) -> int:
    cfg, inv = _control_context(args)
    return oneshot.cmd(
        args.target,
        args.command,
        list(args.args),
        cfg=cfg,
        inventory=inv,
        as_json=getattr(args, "json", False),
        dry_run=getattr(args, "dry_run", False),
    )


def cmd_estop(args: argparse.Namespace) -> int:
    cfg, inv = _control_context(args)
    return oneshot.estop(
        args.target,
        cfg=cfg,
        inventory=inv,
        as_json=getattr(args, "json", False),
        dry_run=getattr(args, "dry_run", False),
    )


# ---- agent / teleop / monitor --------------------------------------------


def _agent_base_url(cfg: Config, inv: Inventory, target: str) -> str:
    address = inv.resolve(target)
    port = int(cfg.agent_bind.rsplit(":", 1)[1])
    return f"http://{address}:{port}"


def cmd_teleop(args: argparse.Namespace) -> int:
    import asyncio

    from agent.auth import load_token
    from pibot.control.client import AgentClient
    from pibot.control.teleop import run_teleop, stdin_key_source

    cfg, inv = _context()
    rate = getattr(args, "rate", None) or cfg.teleop_rate_hz

    async def _drive() -> int:
        client = AgentClient(
            _agent_base_url(cfg, inv, args.target), token=load_token(cfg.agent_token_path)
        )
        await client.connect()
        key_source = stdin_key_source()
        try:
            print("teleop: WASD/arrows drive, space=e-stop, q=quit")
            await run_teleop(client, key_source, rate_hz=rate)
        finally:
            key_source.restore()  # type: ignore[attr-defined]
            await client.close()
        return 0

    return asyncio.run(_drive())


def cmd_monitor(args: argparse.Namespace) -> int:
    import asyncio

    cfg, inv = _context()
    return asyncio.run(
        monitor_mod.monitor(
            args.target,
            cfg=cfg,
            inventory=inv,
            once=getattr(args, "once", False),
            as_json=getattr(args, "json", False),
            as_csv=getattr(args, "as_csv", False),
            interval=getattr(args, "interval", 1.0),
        )
    )


def cmd_agent(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    user_arg = getattr(args, "user", None)
    dry_run = getattr(args, "dry_run", False)
    action = args.agent_action
    if action == "status":
        return agent_ctl.status(args.target, cfg=cfg, inventory=inv, user=user_arg)
    if action == "start":
        return agent_ctl.start(args.target, cfg=cfg, inventory=inv, user=user_arg, dry_run=dry_run)
    if action == "stop":
        return agent_ctl.stop(args.target, cfg=cfg, inventory=inv, user=user_arg, dry_run=dry_run)
    return agent_ctl.logs(args.target, cfg=cfg, inventory=inv, user=user_arg, lines=args.lines)


def cmd_agent_token(args: argparse.Namespace) -> int:
    from agent.auth import generate_token

    cfg, _ = _context()
    path = cfg.agent_token_path
    token = generate_token(path)
    if getattr(args, "json", False):
        print(json.dumps({"token": token, "path": path}))
    else:
        print(f"token: {token}")
        print(f"path:  {path}")
        print("copy this token to the Pi's agent.token (same path) to allow non-loopback access")
    return 0


# ---- deploy / play -------------------------------------------------------


def _repo_root() -> Path:
    """The source tree to deploy (the package's parent — the repo checkout)."""
    return Path(__file__).resolve().parents[1]


def cmd_deploy(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    address = inv.resolve(args.target)
    login = user.resolve_user(address, cfg, explicit=getattr(args, "user", None))
    destination = sshcmd.destination(address, login)
    identity = getattr(args, "identity", None) or cfg.identity
    base = getattr(args, "base", None) or cfg.deploy_base
    port = int(cfg.agent_bind.rsplit(":", 1)[1])

    if getattr(args, "rollback", False):
        return deploy_service.rollback(destination, remote_base=base, port=port, identity=identity)

    src = getattr(args, "src", None) or str(_repo_root())
    dry_run = getattr(args, "dry_run", False)
    result = deploy_sync.deploy(
        destination,
        src_root=src.rstrip("/") + "/",
        remote_base=base,
        identity=identity,
        dry_run=dry_run,
    )
    for path in result.changed:
        print(f"  changed: {path}")
    print(f"release {result.release} ({len(result.changed)} file(s) changed)")
    if dry_run:
        print("dry run — agent not restarted")
        return 0
    return deploy_service.install(
        destination, remote_base=base, port=port, identity=identity, user=login
    )


def _drive_sequence(cfg: Config, inv: Inventory, target: str, steps: list, rate: float) -> int:
    import asyncio

    from agent.auth import load_token
    from pibot.control.client import AgentClient
    from pibot.control.sequence import play

    async def _run() -> int:
        client = AgentClient(
            _agent_base_url(cfg, inv, target), token=load_token(cfg.agent_token_path)
        )
        await client.connect()
        try:
            return await play(client, steps, keepalive_hz=rate)
        finally:
            await client.close()

    return asyncio.run(_run())


def cmd_play(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    steps = load_sequence(Path(args.sequence))
    rate = getattr(args, "rate", None) or cfg.teleop_rate_hz
    if getattr(args, "dry_run", False):
        print(f"[dry-run] {len(steps)} step(s) for {args.target} @ {rate}Hz keepalive:")
        for step in steps:
            args_str = " ".join(f"{k}={v}" for k, v in step.args.items())
            print(f"  t={step.at:>6.2f}s  {step.cmd} {args_str}".rstrip())
        return 0
    return _drive_sequence(cfg, inv, args.target, steps, rate)


# ---- autonomy (VLA policy) -----------------------------------------------


def _run_open_loop(cfg: Config, inv: Inventory, target: str, prompt: str) -> int:
    """Open-loop autonomy: camera + telemetry -> policy server, log actions, NO actuation."""
    from pibot.ml.camera import Camera
    from pibot.ml.openloop import run_open_loop

    address = inv.resolve(target)
    camera = Camera(cfg.camera_device)
    camera.open()

    def state_fn() -> list[float]:
        # robot state vector for the observation (OQ-2: which telemetry fields) — wired to
        # the agent's live telemetry on the robot; the open-loop run reads it each step.
        from agent.telemetry import read_system_stats

        stats = read_system_stats() or {}
        cpu = stats.get("cpu_pct")
        mem = stats.get("mem_pct")
        return [
            float(cpu) if cpu is not None else 0.0,
            float(mem) if mem is not None else 0.0,
        ]

    def log_step(obs: dict | None, action: dict) -> None:
        _log.info("open-loop step: prompt=%r action=%s", prompt, action)

    cfg.policy_host = cfg.policy_host or address
    cfg.prompt = prompt
    try:
        return run_open_loop(cfg, camera, state_fn, on_step=log_step)
    finally:
        camera.close()


def cmd_autonomy(args: argparse.Namespace) -> int:
    cfg, inv = _context()
    prompt = getattr(args, "prompt", None) or cfg.prompt
    if getattr(args, "open_loop", False):
        return _run_open_loop(cfg, inv, args.target, prompt)
    raise UsageError("closed-loop autonomy is gated to M10; run with --open-loop for now")
