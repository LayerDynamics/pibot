"""T10.1 — closed-loop apply_action: policy action -> drive(v,w) -> the M4 safety gate.

The environment never touches a transport directly — it submits through an injected gate
(the agent's AgentSafety.submit on the robot), so clamp/e-stop/deadman always apply
(SPEC-2 FR-4/FR-6). A malformed action actuates nothing (the deadman then stops the robot).
"""

from __future__ import annotations

from pibot.ml.closed_loop import ClosedLoopEnvironment
from pibot.protocol.codec import MessageType


class _Cam:
    def capture(self) -> str:
        return "IMG"


def _env(submit) -> ClosedLoopEnvironment:
    return ClosedLoopEnvironment(_Cam(), state_fn=lambda: [0.0, 0.0], prompt="drive", submit=submit)


def test_apply_action_maps_to_drive_and_submits() -> None:
    sent: list = []
    env = _env(lambda msg: sent.append(msg) or (True, "ok"))
    env.apply_action({"actions": [0.5, -0.3]})
    assert len(sent) == 1
    assert sent[0].type is MessageType.COMMAND and sent[0].name == "drive"
    assert sent[0].args == {"v": 0.5, "w": -0.3}


def test_reset_submits_a_stop() -> None:
    sent: list = []
    env = _env(lambda msg: sent.append(msg) or (True, "ok"))
    env.reset()
    assert sent[-1].name == "stop"


def test_malformed_action_actuates_nothing() -> None:
    sent: list = []
    env = _env(lambda msg: sent.append(msg) or (True, "ok"))
    env.apply_action({"actions": [0.5]})  # missing w -> not a valid drive
    assert sent == []  # nothing submitted; the deadman will stop the robot


def test_unique_seqs_per_command() -> None:
    sent: list = []
    env = _env(lambda msg: sent.append(msg) or (True, "ok"))
    env.apply_action({"actions": [0.1, 0.0]})
    env.apply_action({"actions": [0.2, 0.0]})
    assert sent[0].seq != sent[1].seq
