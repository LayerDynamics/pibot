"""Safety primitives shared by the agent and mirrored in firmware.

Three independent guards stand between a command and a motor:
* :func:`clamp_command` — bound velocity/servo/PWM to configured maxima.
* :class:`EStop` — a latched stop that rejects motion until an explicit ``resume``.
* :class:`Watchdog` — a deadman timer that "expires" if not fed within ``deadman_ms``.

The clock is injectable so the watchdog is tested deterministically.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from pibot.protocol.codec import Message, MessageType

# Commands that remain permitted while e-stop is latched (they reduce or report state).
_SAFE_COMMANDS = frozenset({"stop", "estop", "ping"})
# Commands that actuate and must be bounded / gated.
_MOTION_COMMANDS = frozenset({"drive", "motor", "servo"})


@dataclass
class Limits:
    """Configured actuator maxima used by :func:`clamp_command`."""

    max_v: float = 1.0
    max_w: float = 2.0
    servo_min: float = 0.0
    servo_max: float = 180.0
    max_pwm: int = 255


def _bound(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clamp_command(msg: Message, limits: Limits) -> Message:
    """Return a copy of ``msg`` with motion arguments bounded to ``limits``."""
    if msg.type is not MessageType.COMMAND:
        return msg
    if msg.name == "drive":
        args = {
            "v": _bound(float(msg.args["v"]), -limits.max_v, limits.max_v),
            "w": _bound(float(msg.args["w"]), -limits.max_w, limits.max_w),
        }
    elif msg.name == "servo":
        args = {
            "id": msg.args["id"],
            "deg": _bound(float(msg.args["deg"]), limits.servo_min, limits.servo_max),
        }
    elif msg.name == "motor":
        pwm = int(_bound(float(msg.args["pwm"]), -limits.max_pwm, limits.max_pwm))
        args = {"id": msg.args["id"], "pwm": pwm}
    else:
        return msg
    return Message(msg.type, msg.seq, msg.name, args)


class EStop:
    """A latched emergency stop. While latched, only safe commands are allowed."""

    def __init__(self) -> None:
        self._latched = False

    @property
    def latched(self) -> bool:
        return self._latched

    def trip(self) -> None:
        self._latched = True

    def resume(self) -> None:
        self._latched = False

    def allows(self, msg: Message) -> bool:
        """Whether ``msg`` may be sent given the current latch state."""
        if not self._latched:
            return True
        if msg.type is not MessageType.COMMAND:
            return True
        return msg.name not in _MOTION_COMMANDS or msg.name in _SAFE_COMMANDS


class Watchdog:
    """Deadman timer: :meth:`expired` is True if not :meth:`feed`-d within the window."""

    def __init__(self, deadman_ms: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._deadman = deadman_ms / 1000.0
        self._clock = clock
        self._last = clock()

    def feed(self) -> None:
        self._last = self._clock()

    def expired(self) -> bool:
        return (self._clock() - self._last) > self._deadman

    def time_left_ms(self) -> float:
        return max(0.0, (self._deadman - (self._clock() - self._last)) * 1000.0)
