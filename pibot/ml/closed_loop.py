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
    if vec is not None and hasattr(vec, "__iter__"):
        return list(vec)
    return []


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


def run_closed_loop(  # pragma: no cover - hardware: real transport + policy server + camera
    cfg: Any, camera: Any, *, limits: Any, control_hz: float
) -> int:
    """Drive the robot from the remote VLA policy, every action gated by the M4 safety stack.

    Builds the same transport + :class:`~agent.safety.AgentSafety` wiring ``pibotd`` uses (clamp
    + latched e-stop + deadman), connects to the policy server, then runs
    ``observe → infer → gated drive`` at ``control_hz`` until the episode ends. The robot is
    always left stopped on exit. ``limits`` is the (optionally governed) speed cap from the CLI.

    Fail-safe layering (FR-6): the host deadman (ticked each cycle) stops the robot when the
    control loop is *alive but not feeding* accepted commands (e.g. a malformed/empty chunk). A
    **hard stall** — ``infer()`` blocking on a wedged server or dropped link — blocks this
    single-threaded loop, so the *independent* **firmware watchdog** on the ESP32 is the backstop
    that halts the motors there. Both layers are verified on hardware in T10.6; the host-deadman
    primitive is unit-proven in ``tests/test_autonomy_drop_to_stop.py``.
    """
    import time

    from openpi_client import action_chunk_broker, websocket_client_policy

    from agent.pibotd import build_transport
    from agent.safety import AgentSafety
    from pibot.ml.state import VelocityState

    transport = build_transport(cfg)
    transport.open()
    velocity = VelocityState()  # state = the last commanded velocity [v, ω] (OQ-2)
    # max_rate_hz=0: the loop's own pacing sets cadence; clamp/e-stop/deadman are the guards.
    safety = AgentSafety(
        transport.send,
        limits=limits,
        deadman_ms=cfg.watchdog_ms,
        max_rate_hz=0,
        encoding=cfg.encoding,
    )
    env = ClosedLoopEnvironment(camera, velocity.vector, cfg.prompt, submit=safety.submit)
    policy = action_chunk_broker.ActionChunkBroker(
        websocket_client_policy.WebsocketClientPolicy(host=cfg.policy_host, port=cfg.policy_port),
        action_horizon=cfg.action_horizon,
    )
    period = 1.0 / control_hz if control_hz > 0 else 0.0
    try:
        env.reset()  # begin from a known stop
        while not env.is_episode_complete():
            action = policy.infer(env.get_observation())
            env.apply_action(action)  # -> drive(v, ω) through the safety gate
            velocity.update(action)  # advance the state estimate for the next observation
            safety.tick()  # host deadman: stop if the loop is alive but no command was accepted
            if period:
                time.sleep(period)
    finally:
        env.reset()  # always leave the robot stopped
        transport.close()
    return 0
