"""PibotEnvironment — the seam between the openpi runtime and the robot (SPEC-2 §3.2).

Implements openpi's ``Environment`` ABC contract (``reset`` / ``is_episode_complete`` /
``get_observation`` / ``apply_action``) by **duck typing**: it does not import
``openpi_client`` at module load, so it installs and unit-tests without the ``pibot[ml]``
extra. On the robot it is handed to ``openpi_client.runtime.Runtime``, which simply calls
these methods each control step.

``get_observation`` assembles the Appendix-B observation (camera frame + robot state +
prompt). ``apply_action`` is **gated until M10** — the open-loop env (M8 T8.4) overrides it
to log only, and the closed-loop actuation path (through the M4 safety gate) lands in M10.
The camera and the state source are injected so the environment is hardware-free in tests.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pibot.ml.types import Observation


class PibotEnvironment:
    def __init__(
        self,
        camera: Any,
        state_fn: Callable[[], list[float]],
        prompt: str = "",
        *,
        stop_fn: Callable[[], None] | None = None,
    ) -> None:
        self._camera = camera
        self._state_fn = state_fn  # robot state vector from M3/M4 telemetry (OQ-2)
        self._prompt = prompt
        self._stop_fn = stop_fn  # called on reset() — halt the robot at episode boundaries

    def reset(self) -> None:
        """Halt the robot at an episode boundary (a fresh episode starts stopped)."""
        if self._stop_fn is not None:
            self._stop_fn()

    def is_episode_complete(self) -> bool:
        return False  # continuous driving; a goal predicate could end an episode later

    def get_observation(self) -> dict[str, Any]:
        return Observation(
            image=self._camera.capture(),
            state=list(self._state_fn()),
            prompt=self._prompt,
        ).to_dict()

    def apply_action(self, action: dict[str, Any]) -> None:
        raise NotImplementedError(
            "closed-loop actuation lands in M10 (T10.1, through the M4 safety gate); "
            "the open-loop environment (M8 T8.4) overrides this to log only"
        )
