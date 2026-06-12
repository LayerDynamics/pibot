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

from pibot import discovery
from pibot.config import Config, load_config
from pibot.connection import commands, keys, transfer, tunnel
from pibot.control import oneshot
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
    p_eeprom.set_defaults(func=cmd_eeprom)

    p_prov = sub.add_parser("provision", parents=[g], help="clone/restore the Pi NVMe")
    prov_sub = p_prov.add_subparsers(dest="action", required=True)
    p_clone = prov_sub.add_parser("clone", parents=[g, t], help="back up the Pi NVMe to an image")
    p_clone.add_argument("target")
    p_clone.add_argument("--to", required=True, dest="to_file", help="output image (.img.gz)")
    p_clone.add_argument("--device", default="/dev/nvme0n1", help="source device on the Pi")
    p_clone.add_argument("--shrink", action="store_true", default=argparse.SUPPRESS)
    p_clone.set_defaults(func=cmd_provision_clone)
    p_restore = prov_sub.add_parser("restore", parents=[g, t], help="restore an image to the Pi")
    p_restore.add_argument("target")
    p_restore.add_argument("--from", required=True, dest="from_file", help="image to restore")
    p_restore.add_argument("--device", default="/dev/nvme0n1", help="target device on the Pi")
    p_restore.add_argument("--confirm", action="store_true", default=argparse.SUPPRESS)
    p_restore.set_defaults(func=cmd_provision_restore)

    p_fw = sub.add_parser("firmware", parents=[g], help="build/flash Arduino firmware")
    fw_sub = p_fw.add_subparsers(dest="action", required=True)
    p_fw_build = fw_sub.add_parser("build", parents=[g], help="compile a sketch")
    p_fw_build.add_argument("sketch")
    p_fw_build.add_argument("--fqbn", required=True, help="e.g. arduino:avr:uno")
    p_fw_build.set_defaults(func=cmd_firmware_build)
    p_fw_flash = fw_sub.add_parser("flash", parents=[g], help="upload a sketch")
    p_fw_flash.add_argument("sketch")
    p_fw_flash.add_argument("--fqbn", required=True, help="e.g. arduino:avr:uno")
    p_fw_flash.add_argument("--port", required=True, help="e.g. /dev/ttyACM0")
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
    p_cmd.set_defaults(func=cmd_cmd)

    p_estop = sub.add_parser("estop", parents=[g], help="emergency-stop the robot")
    p_estop.add_argument("target")
    p_estop.add_argument(
        "--transport", dest="transport_override", choices=_transports, default=argparse.SUPPRESS
    )
    p_estop.set_defaults(func=cmd_estop)

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
    user = getattr(args, "user", None)
    confirm = getattr(args, "confirm", False)
    if args.action == "status":
        return eeprom.status(args.target, cfg=cfg, inventory=inv, user=user)
    if args.action == "config":
        return eeprom.show_config(args.target, cfg=cfg, inventory=inv, user=user)
    if args.action == "update":
        return eeprom.update(args.target, cfg=cfg, inventory=inv, user=user, confirm=confirm)
    if not args.value:
        raise UsageError("boot-order requires a value, e.g. 0xf416")
    return eeprom.set_boot_order(
        args.target, args.value, cfg=cfg, inventory=inv, user=user, confirm=confirm
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
    )


def cmd_firmware_build(args: argparse.Namespace) -> int:
    return firmware.build(args.sketch, fqbn=args.fqbn)


def cmd_firmware_flash(args: argparse.Namespace) -> int:
    return firmware.flash(args.sketch, fqbn=args.fqbn, port=args.port)


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
    )


def cmd_estop(args: argparse.Namespace) -> int:
    cfg, inv = _control_context(args)
    return oneshot.estop(args.target, cfg=cfg, inventory=inv, as_json=getattr(args, "json", False))
