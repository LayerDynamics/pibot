"""Open-loop autonomy: stream real observations, log the policy's actions, NEVER actuate.

The bring-up gate before any closed-loop motion (SPEC-2 FR-11 / M8 Phase B). The proof
that the robot can't move is structural: :class:`OpenLoopEnvironment` carries **no
transport**, so ``apply_action`` only records the ``(observation, action)`` pair (fed to
the dataset recorder in M9) and returns. The openpi ``Runtime`` + ``ActionChunkBroker`` +
``WebsocketClientPolicy`` are wired lazily in :func:`run_open_loop` on the robot.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pibot.config import Config
from pibot.ml.pibot_environment import PibotEnvironment

StepSink = Callable[[dict[str, Any] | None, dict[str, Any]], None]


class OpenLoopEnvironment(PibotEnvironment):
    """A :class:`PibotEnvironment` whose ``apply_action`` logs only — no actuation path."""

    def __init__(
        self,
        camera: Any,
        state_fn: Callable[[], list[float]],
        prompt: str = "",
        *,
        on_step: StepSink | None = None,
    ) -> None:
        super().__init__(camera, state_fn, prompt, stop_fn=None)
        self._on_step = on_step
        self._last_obs: dict[str, Any] | None = None

    def get_observation(self) -> dict[str, Any]:
        self._last_obs = super().get_observation()
        return self._last_obs

    def apply_action(self, action: dict[str, Any]) -> None:
        # OPEN LOOP: record the (obs, action) pair; there is no transport, so nothing can
        # be sent to the motors. This overrides the base class's M10 NotImplementedError.
        if self._on_step is not None:
            self._on_step(self._last_obs, action)


def run_open_loop(
    cfg: Config,
    camera: Any,
    state_fn: Callable[[], list[float]],
    *,
    on_step: StepSink | None = None,
) -> int:  # pragma: no cover - wires real openpi Runtime/broker/policy on the robot
    """Stream observations to the policy server and log actions; never actuate."""
    from openpi_client import action_chunk_broker, websocket_client_policy
    from openpi_client.runtime import agents, runtime

    policy = action_chunk_broker.ActionChunkBroker(
        websocket_client_policy.WebsocketClientPolicy(host=cfg.policy_host, port=cfg.policy_port),
        action_horizon=cfg.action_horizon,
    )
    env = OpenLoopEnvironment(camera, state_fn, cfg.prompt, on_step=on_step)
    rt = runtime.Runtime(
        environment=env,
        agent=agents.policy_agent.PolicyAgent(policy),
        subscribers=[],
        max_hz=cfg.control_hz,
    )
    rt.run()
    return 0
