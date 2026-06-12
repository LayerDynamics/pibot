"""Agent-central safety: the single place every command passes before the transport.

Wraps the M3 primitives (:class:`EStop`, :class:`Watchdog`, :func:`clamp_command`) into a
state machine that the agent's transport loop drives. Any trip — e-stop latched, or the
deadman watchdog expiring because the operator's command stream went quiet — emits a
``stop`` frame to the robot. This is the host-side half of the layered fail-safe; the
firmware enforces its own independent watchdog as the backstop.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from pibot.control.safety import EStop, Limits, Watchdog, clamp_command
from pibot.protocol.codec import Message, MessageType, SeqTracker, encode

_MOTION = frozenset({"drive", "motor", "servo"})

SendFn = Callable[[bytes], None]


class AgentSafety:
    def __init__(
        self,
        send: SendFn,
        *,
        limits: Limits | None = None,
        deadman_ms: float = 300,
        max_rate_hz: float = 50,
        encoding: str = "ascii",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._send = send
        self._limits = limits or Limits()
        self._encoding = encoding
        self._clock = clock
        self._estop = EStop()
        self._wd = Watchdog(deadman_ms, clock=clock)
        self._min_interval = 1.0 / max_rate_hz if max_rate_hz > 0 else 0.0
        self._last_motion_t: float | None = None
        self._seq = SeqTracker()
        self._stopped = False

    @property
    def latched(self) -> bool:
        return self._estop.latched

    def submit(self, msg: Message) -> tuple[bool, str]:
        """Validate, clamp, gate, and (if allowed) send ``msg``. Returns ``(sent, reason)``."""
        if not self._estop.allows(msg):
            return False, "estop"
        is_motion = msg.type is MessageType.COMMAND and msg.name in _MOTION
        if is_motion and self._rate_limited():
            return False, "rate"
        clamped = clamp_command(msg, self._limits)
        self._send(encode(clamped, self._encoding))
        self._wd.feed()  # any accepted command keeps the deadman alive
        if is_motion:
            self._last_motion_t = self._clock()
        self._stopped = clamped.name in ("stop", "estop")
        return True, "ok"

    def _rate_limited(self) -> bool:
        if self._last_motion_t is None or self._min_interval <= 0:
            return False
        return (self._clock() - self._last_motion_t) < self._min_interval

    def trip_estop(self) -> None:
        """Latch e-stop and immediately command a stop."""
        self._estop.trip()
        self._emit_stop()

    def resume(self) -> None:
        self._estop.resume()

    def tick(self) -> None:
        """Call periodically: if the deadman expired, command a stop (once)."""
        if self._wd.expired() and not self._stopped:
            self._emit_stop()

    def _emit_stop(self) -> None:
        self._send(
            encode(Message(MessageType.COMMAND, self._seq.next(), "stop", {}), self._encoding)
        )
        self._stopped = True
        self._wd.feed()  # reset so we don't spam stop frames every tick
