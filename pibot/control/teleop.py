"""Keyboard teleoperation: map keys to drive/stop/e-stop and stream them to the agent.

The key→action mapping is pure and tested. The drive loop sends one command per tick at
a fixed rate; an idle/released key maps to ``stop`` so the robot halts promptly, while a
dropped connection (no sends) trips the agent's deadman watchdog. Spacebar latches e-stop.
The raw-terminal key reader is the only untested shell (exercised in the hardware E2E).
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pibot.control.client import AgentClient


@dataclass(frozen=True)
class Action:
    kind: str  # "drive" | "stop" | "estop" | "quit"
    v: float = 0.0
    w: float = 0.0


def key_to_action(key: str | None, *, speed: float = 0.5, turn: float = 1.0) -> Action:
    """Map a keypress to a teleop action. Idle/unknown keys -> stop."""
    k = (key or "").lower()
    if k in ("w", "up"):
        return Action("drive", speed, 0.0)
    if k in ("s", "down"):
        return Action("drive", -speed, 0.0)
    if k in ("a", "left"):
        return Action("drive", 0.0, turn)
    if k in ("d", "right"):
        return Action("drive", 0.0, -turn)
    if k in (" ", "space"):
        return Action("estop")
    if k in ("q", "\x03", "\x1b"):  # q, Ctrl-C, Esc
        return Action("quit")
    return Action("stop")


async def apply_action(client: AgentClient, action: Action) -> dict[str, Any] | None:
    """Send ``action`` to the agent; return the reply (or None for quit)."""
    if action.kind == "drive":
        return await client.send_command("drive", {"v": action.v, "w": action.w})
    if action.kind == "stop":
        return await client.send_command("stop", {})
    if action.kind == "estop":
        return await client.estop()
    return None


async def run_teleop(
    client: AgentClient,
    key_source: Callable[[], str | None],
    *,
    rate_hz: float = 20.0,
    speed: float = 0.5,
    turn: float = 1.0,
    on_tick: Callable[[Action, dict[str, Any] | None], None] | None = None,
    max_ticks: int | None = None,
) -> None:
    """Drive loop: read a key, map to an action, send it, repeat at ``rate_hz``."""
    interval = 1.0 / rate_hz
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        action = key_to_action(key_source(), speed=speed, turn=turn)
        if action.kind == "quit":
            await client.send_command("stop", {})
            break
        result = await apply_action(client, action)
        if on_tick is not None:
            on_tick(action, result)
        ticks += 1
        await asyncio.sleep(interval)


def stdin_key_source() -> Callable[[], str | None]:
    """Return a non-blocking key reader for a raw terminal (real teleop)."""
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)

    def read_key() -> str | None:  # pragma: no cover - interactive terminal I/O
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":  # arrow keys arrive as an escape sequence
            seq = sys.stdin.read(2) if select.select([sys.stdin], [], [], 0)[0] else ""
            return {"[A": "up", "[B": "down", "[C": "right", "[D": "left"}.get(seq, "\x1b")
        return ch

    read_key.restore = lambda: termios.tcsetattr(fd, termios.TCSADRAIN, old)  # type: ignore[attr-defined]
    return read_key
