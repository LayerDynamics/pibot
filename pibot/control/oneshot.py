"""One-shot ``pibot cmd`` / ``pibot estop`` — send a single command and await its ACK.

Builds a typed :class:`Message` from CLI tokens, clamps it, gates it through an e-stop,
sends it over the configured transport, and waits for the matching ACK (a NAK or a
timeout becomes an error). In M4 this same path runs inside the agent with a persistent
e-stop and the live transport; here each call is self-contained.
"""

from __future__ import annotations

import json
import time

from pibot.config import Config
from pibot.control.safety import EStop, Limits, clamp_command
from pibot.errors import ConnectionError, UsageError
from pibot.inventory import Inventory
from pibot.protocol.codec import (
    DecodeError,
    Message,
    MessageType,
    SeqTracker,
    decode,
    encode,
)
from pibot.transport.base import Transport

# command name -> [(arg name, parser)]
_CMD_ARGS: dict[str, list[tuple[str, type]]] = {
    "drive": [("v", float), ("w", float)],
    "servo": [("id", int), ("deg", float)],
    "motor": [("id", int), ("pwm", int)],
    "set": [("param", str), ("value", float)],
    "stop": [],
    "estop": [],
    "ping": [],
}


def build_message(name: str, raw_args: list[str], seq: int) -> Message:
    """Build a COMMAND message from CLI tokens, validating arity and types."""
    spec = _CMD_ARGS.get(name)
    if spec is None:
        raise UsageError(f"unknown command {name!r}; known: {', '.join(sorted(_CMD_ARGS))}")
    if len(raw_args) != len(spec):
        names = ", ".join(a for a, _ in spec)
        raise UsageError(f"{name} takes {len(spec)} arg(s) [{names}], got {len(raw_args)}")
    args: dict[str, object] = {}
    for (arg_name, parser), raw in zip(spec, raw_args, strict=True):
        try:
            args[arg_name] = parser(raw)
        except ValueError as exc:
            raise UsageError(f"{name} arg {arg_name}={raw!r} is not a {parser.__name__}") from exc
    return Message(MessageType.COMMAND, seq, name, args)


def send_command(
    transport: Transport, msg: Message, *, encoding: str = "ascii", timeout: float = 1.0
) -> Message:
    """Send ``msg`` and return the matching ACK, or raise on NAK / timeout."""
    transport.send(encode(msg, encoding))
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ConnectionError(f"no ACK for {msg.name} (seq {msg.seq}) within {timeout}s")
        frame = transport.recv(remaining)
        if frame is None:
            continue
        try:
            reply = decode(frame, encoding)
        except DecodeError:
            continue  # ignore line noise; keep waiting for our ACK
        if reply.seq != msg.seq:
            continue  # telemetry or another command's ack
        if reply.type is MessageType.ACK:
            return reply
        if reply.type is MessageType.NAK:
            raise ConnectionError(f"robot rejected {msg.name}: NAK {reply.reason}")


def cmd(
    target: str,
    name: str,
    raw_args: list[str],
    *,
    cfg: Config,
    inventory: Inventory,
    transport: Transport | None = None,
    estop_state: EStop | None = None,
    as_json: bool = False,
    dry_run: bool = False,
) -> int:
    """Build, clamp, gate, send one command to ``target``; await its ACK."""
    address = inventory.resolve(target)

    msg = clamp_command(build_message(name, raw_args, SeqTracker().next()), Limits())
    if (estop_state or EStop()).allows(msg) is False:
        raise UsageError("e-stop is latched; refusing to send a motion command")

    if dry_run:
        frame = encode(msg, cfg.encoding).decode(cfg.encoding).rstrip()
        print(f"[dry-run] would send to {address} via {cfg.transport}: {frame}")
        return 0

    own_transport = transport is None
    transport = transport or _build_transport(cfg, address)
    try:
        if not transport.is_open:
            transport.open()
        reply = send_command(transport, msg, encoding=cfg.encoding, timeout=cfg.cmd_timeout)
    finally:
        if own_transport:
            transport.close()

    if as_json:
        print(
            json.dumps({"target": address, "command": name, "args": msg.args, "ack_seq": reply.seq})
        )
    else:
        print(f"{name} -> ACK (seq {reply.seq})")
    return 0


def estop(
    target: str,
    *,
    cfg: Config,
    inventory: Inventory,
    transport: Transport | None = None,
    as_json: bool = False,
    dry_run: bool = False,
) -> int:
    """Send the highest-priority stop to ``target``."""
    return cmd(
        target,
        "estop",
        [],
        cfg=cfg,
        inventory=inventory,
        transport=transport,
        as_json=as_json,
        dry_run=dry_run,
    )


def _build_transport(cfg: Config, address: str) -> Transport:
    if cfg.transport == "tcp":
        from pibot.transport.tcp import TcpTransport

        return TcpTransport(address, cfg.tcp_port)
    if cfg.transport == "serial":
        from pibot.transport.serial import SerialTransport

        return SerialTransport(cfg.serial_port, cfg.serial_baud)
    if cfg.transport == "responder":
        from pibot.transport.responder import ResponderTransport

        return ResponderTransport(cfg.encoding)
    if cfg.transport == "loopback":
        from pibot.transport.loopback import LoopbackTransport

        return LoopbackTransport()
    raise UsageError(f"unknown transport {cfg.transport!r}")
