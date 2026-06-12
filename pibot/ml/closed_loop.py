"""Closed-loop autonomy: the policy drives the robot, behind the M4 safety gate (M10).

:class:`ClosedLoopEnvironment` maps each policy action ``[v, ω]`` to a ``drive(v, ω)``
command and **submits it through an injected gate** — on the robot that gate is the agent's
``AgentSafety.submit`` (clamp + latched e-stop + deadman), so the VLA can never bypass local
safety (SPEC-2 FR-4/FR-6/FR-19). A malformed action submits nothing; the deadman then stops
the robot. The gate is injected, so this is unit-tested without the agent or a transport.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pibot.ml.pibot_environment import PibotEnvironment
from pibot.protocol.codec import Message, MessageType, SeqTracker

# (sent, reason) — the contract of AgentSafety.submit
SubmitFn = Callable[[Message], tuple[bool, str]]


def _action_vector(action: Any) -> list[float]:
    vec = action.get("actions") if isinstance(action, dict) else action
    return list(vec) if vec is not None else []


class ClosedLoopEnvironment(PibotEnvironment):
    def __init__(
        self,
        camera: Any,
        state_fn: Callable[[], list[float]],
        prompt: str = "",
        *,
        submit: SubmitFn,
        seq: SeqTracker | None = None,
    ) -> None:
        super().__init__(camera, state_fn, prompt, stop_fn=self._send_stop)
        self._submit = submit
        self._seq = seq or SeqTracker()

    def apply_action(self, action: dict[str, Any]) -> None:
        cmd = self._action_to_command(_action_vector(action))
        if cmd is not None:
            self._submit(cmd)  # through clamp + e-stop + deadman

    def _action_to_command(self, vec: list[float]) -> Message | None:
        if len(vec) < 2:
            return None  # not a valid drive — actuate nothing, let the deadman stop
        return Message(
            MessageType.COMMAND, self._seq.next(), "drive", {"v": float(vec[0]), "w": float(vec[1])}
        )

    def _send_stop(self) -> None:
        self._submit(Message(MessageType.COMMAND, self._seq.next(), "stop", {}))
