"""The rover's proprioceptive state for the VLA (SPEC-2 OQ-2).

PiBot has no encoders/IMU, so its meaningful proprioception is the **last commanded
velocity** ``[v, ω]`` — what the robot is currently doing. :class:`VelocityState` is
updated each control step from the applied action and read back as the observation
``state`` on the next step (so the model sees the velocity it just commanded).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class VelocityState:
    v: float = 0.0
    w: float = 0.0

    def update(self, action: Any) -> None:
        """Set ``[v, ω]`` from a per-step action (dict ``{"actions": vec}`` or a raw vector)."""
        vec = action.get("actions") if isinstance(action, dict) else action
        try:
            if vec is not None and len(vec) >= 2:
                self.v, self.w = float(vec[0]), float(vec[1])
        except (TypeError, ValueError, IndexError, KeyError):
            pass

    def vector(self) -> list[float]:
        return [self.v, self.w]
