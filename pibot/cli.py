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
from pibot.errors import PibotError, UsageError
from pibot.inventory import Inventory, InventoryRecord
from pibot.logging import configure_logging, get_logger

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
