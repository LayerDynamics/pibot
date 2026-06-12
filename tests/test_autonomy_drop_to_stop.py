"""T10.3 — drop-to-stop: if the policy stream stalls, the deadman stops the robot (FR-6).

A VLA can hang — the server can wedge, the network can drop, an inference can take seconds.
The closed-loop environment shares the agent's deadman watchdog: every accepted drive feeds
it, and a periodic ``tick`` emits a ``stop`` once the deadman expires. We drive an action,
advance an *injected* clock past the deadman window, and assert the very next tick puts a
``stop`` on the wire — through the real :class:`~agent.safety.AgentSafety`, no mocked timer.

The malformed-action case is the same fail-safe end-to-end: a bad action actuates nothing,
so nothing feeds the deadman, so the robot coasts to a commanded stop instead of running open.
"""

from __future__ import annotations

from agent.safety import AgentSafety
from pibot.ml.closed_loop import ClosedLoopEnvironment
from pibot.protocol.codec import decode


class _Cam:
    def capture(self) -> str:
        return "IMG"


class _Clock:
    """A hand-cranked monotonic clock so the deadman is exercised without real sleeps."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _gate(sent: list[bytes], clock: _Clock) -> AgentSafety:
    return AgentSafety(sent.append, deadman_ms=300, max_rate_hz=0, clock=clock)


def _env(safety: AgentSafety) -> ClosedLoopEnvironment:
    return ClosedLoopEnvironment(
        _Cam(), state_fn=lambda: [0.0, 0.0], prompt="drive", submit=safety.submit
    )


def test_deadman_stops_when_policy_stream_goes_quiet() -> None:
    clock = _Clock()
    sent: list[bytes] = []
    safety = _gate(sent, clock)
    env = _env(safety)

    env.apply_action({"actions": [0.5, 0.0]})  # policy commands a drive at t=0
    assert decode(sent[-1]).name == "drive"

    clock.advance(0.5)  # ...then goes silent, well past the 300 ms deadman
    safety.tick()

    assert decode(sent[-1]).name == "stop"


def test_tick_within_the_deadman_window_does_not_stop() -> None:
    clock = _Clock()
    sent: list[bytes] = []
    safety = _gate(sent, clock)
    env = _env(safety)

    env.apply_action({"actions": [0.5, 0.0]})
    before = list(sent)
    clock.advance(0.1)  # still inside the 300 ms window
    safety.tick()

    assert sent == before, "tick must emit nothing while the deadman is alive"
    assert decode(sent[-1]).name == "drive"


def test_malformed_action_lets_the_deadman_fire() -> None:
    clock = _Clock()
    sent: list[bytes] = []
    safety = _gate(sent, clock)
    env = _env(safety)

    env.apply_action({"actions": [0.5, 0.0]})  # prime the deadman with one good drive
    clock.advance(0.5)
    env.apply_action({"actions": [0.5]})  # malformed -> submits nothing -> never feeds the deadman
    safety.tick()

    assert decode(sent[-1]).name == "stop", "a stalled/garbage policy must drop the robot to stop"
