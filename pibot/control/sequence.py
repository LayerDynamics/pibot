"""``pibot play`` — scripted motion from a timed sequence file.

A sequence is a YAML (or JSON — a YAML subset) list of ``{at: seconds, cmd, args}``
steps. :func:`play` dispatches each step at its scheduled offset *through the agent's
control path*, so every command still passes the agent's safety gates (clamp, e-stop,
rate limit). Between steps the scheduler re-sends the held command at ``keepalive_hz``
so the deadman watchdog never trips mid-sequence — and if the agent latches e-stop
(or a step *is* an e-stop), the sequence aborts immediately.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml

from pibot.errors import PibotError

_MOTION = frozenset({"drive", "motor", "servo"})


class SequenceError(PibotError):
    """The motion sequence file is malformed."""


@dataclass
class Step:
    """One scheduled command: dispatch ``cmd(args)`` at ``at`` seconds from start."""

    at: float
    cmd: str
    args: dict[str, Any] = field(default_factory=dict)


class _Client(Protocol):
    async def send_command(
        self, cmd: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...
    async def estop(self) -> dict[str, Any]: ...


def load_sequence(source: str | Path) -> list[Step]:
    """Parse a YAML/JSON sequence into time-sorted :class:`Step`s (raises on malformed)."""
    text = Path(source).read_text(encoding="utf-8") if _is_path(source) else str(source)
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SequenceError(f"could not parse sequence: {exc}") from exc
    if not isinstance(data, list):
        raise SequenceError("sequence must be a list of {at, cmd, args} steps")
    steps: list[Step] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict) or "at" not in item or "cmd" not in item:
            raise SequenceError(f"step {i}: each step needs 'at' and 'cmd'")
        args = item.get("args") or {}
        if not isinstance(args, dict):
            raise SequenceError(f"step {i}: 'args' must be a mapping")
        steps.append(Step(float(item["at"]), str(item["cmd"]), dict(args)))
    return sorted(steps, key=lambda s: s.at)


def _is_path(source: str | Path) -> bool:
    if isinstance(source, Path):
        return True
    # a one-liner with a newline or YAML/JSON punctuation is inline text, not a path
    return "\n" not in source and source.strip().endswith((".yaml", ".yml", ".json"))


async def _dispatch(client: _Client, step: Step) -> dict[str, Any]:
    if step.cmd == "estop":
        return await client.estop()
    return await client.send_command(step.cmd, step.args)


def _aborted(step: Step, reply: dict[str, Any]) -> bool:
    if step.cmd == "estop":
        return True
    return reply.get("rejected") == "estop" or reply.get("estop") is True


async def play(
    client: _Client,
    steps: list[Step],
    *,
    keepalive_hz: float = 10.0,
    final_stop: bool = True,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> int:
    """Run a motion sequence; return 0 on completion, non-zero if e-stop aborted it."""
    if not steps:
        return 0
    interval = 1.0 / keepalive_hz if keepalive_hz > 0 else 0.0
    start = clock()
    end = steps[-1].at
    idx = 0
    current: Step | None = None
    while True:
        now = clock() - start
        while idx < len(steps) and steps[idx].at <= now:
            current = steps[idx]
            idx += 1
            reply = await _dispatch(client, current)
            if _aborted(current, reply):
                return 1  # e-stop latched -> abort the rest of the sequence
        if idx >= len(steps) and now >= end:
            break
        # hold the current motion (and feed the agent deadman) until the next step
        if current is not None and current.cmd in _MOTION:
            reply = await _dispatch(client, current)
            if _aborted(current, reply):
                return 1
        await sleep(interval)
    if final_stop:
        await client.send_command("stop", {})
    return 0
