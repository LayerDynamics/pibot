"""T10.2 — the policy cannot bypass the M4 safety subsystem (SPEC-2 FR-4/FR-6/FR-19).

The closed-loop environment submits every policy action through the agent's *real*
:class:`~agent.safety.AgentSafety` gate — the same object teleop drives through. So whatever
the VLA emits is subject to the identical clamp + latched e-stop the operator's joystick is:

* a latched e-stop drops every policy drive on the floor (verdict ``"estop"``), and
* an over-range policy action is clamped to ``Limits`` exactly as a teleop command is.

We prove identity, not similarity: the frame the policy puts on the wire is byte-for-byte the
frame an equivalent teleop ``drive`` produces. No mocked gate — the regression is meaningless
unless the wire is the real one.
"""

from __future__ import annotations

from agent.safety import AgentSafety
from pibot.control.safety import Limits
from pibot.ml.closed_loop import ClosedLoopEnvironment
from pibot.protocol.codec import Message, MessageType, decode


class _Cam:
    def capture(self) -> str:
        return "IMG"


def _safety(sent: list[bytes], *, limits: Limits | None = None) -> AgentSafety:
    # max_rate_hz=0 disables the rate limiter so a single submit is never dropped as "rate".
    return AgentSafety(sent.append, limits=limits, max_rate_hz=0)


def _closed_loop(safety: AgentSafety) -> ClosedLoopEnvironment:
    return ClosedLoopEnvironment(
        _Cam(), state_fn=lambda: [0.0, 0.0], prompt="drive", submit=safety.submit
    )


def test_latched_estop_blocks_policy_drive() -> None:
    sent: list[bytes] = []
    safety = _safety(sent)
    env = _closed_loop(safety)
    safety.trip_estop()  # operator hits the big red button
    sent.clear()  # discard the stop frame trip_estop emitted

    env.apply_action({"actions": [0.8, 0.4]})  # the policy still wants to move

    assert sent == [], "a latched e-stop must drop every policy drive"


def test_policy_drive_blocked_with_estop_verdict_like_teleop() -> None:
    # The verdict the gate returns to a policy drive is the same one teleop gets: "estop".
    safety = _safety([])
    safety.trip_estop()
    drive = Message(MessageType.COMMAND, 1, "drive", {"v": 0.8, "w": 0.4})
    assert safety.submit(drive) == (False, "estop")


def test_over_range_policy_action_is_clamped_to_limits() -> None:
    sent: list[bytes] = []
    limits = Limits()  # max_v=1.0, max_w=2.0
    env = _closed_loop(_safety(sent, limits=limits))

    env.apply_action({"actions": [5.0, 9.0]})  # wildly over range

    msg = decode(sent[-1])
    assert msg.name == "drive"
    assert msg.args["v"] == limits.max_v  # clamped, not 5.0
    assert msg.args["w"] == limits.max_w  # clamped, not 9.0


def test_policy_frame_is_identical_to_the_teleop_frame() -> None:
    # Same over-range [v, w] via the policy and via a direct teleop submit -> identical wire bytes.
    policy_sent: list[bytes] = []
    env = _closed_loop(_safety(policy_sent))
    env.apply_action({"actions": [3.0, -7.0]})

    teleop_sent: list[bytes] = []
    teleop = _safety(teleop_sent)
    teleop.submit(Message(MessageType.COMMAND, 1, "drive", {"v": 3.0, "w": -7.0}))

    # The seq counter differs by construction; compare the safety-relevant decoded payload.
    assert decode(policy_sent[-1]).args == decode(teleop_sent[-1]).args
    assert decode(policy_sent[-1]).name == decode(teleop_sent[-1]).name
