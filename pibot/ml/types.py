"""Observation/Action contract types — the SPEC-2 Appendix-B wire schema.

The on-robot client serializes an :class:`Observation` to exactly
``{image: {base_0_rgb}, state, prompt}`` and reads an :class:`Action` per step out of the
policy server's ``{actions: [horizon, dim]}`` reply. Image data is opaque (``Any``: a
numpy ``uint8[224,224,3]`` on the robot) so this module imports no numpy — the ml-import
isolation guard (tests/test_ml_isolation.py) keeps holding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Observation:
    """One observation: a camera frame, the robot state vector, and the task prompt."""

    image: Any  # uint8[224,224,3] on the robot (numpy); opaque here
    state: list[float]
    prompt: str
    image_key: str = "base_0_rgb"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the Appendix-B observation dict (state copied, not aliased)."""
        return {
            "image": {self.image_key: self.image},
            "state": list(self.state),
            "prompt": self.prompt,
        }


@dataclass(frozen=True)
class Action:
    """One control step's action vector, e.g. ``[v, ω, servo…]`` (post-PibotOutputs)."""

    vector: list[float]

    @classmethod
    def from_reply(cls, reply: dict[str, Any], step: int = 0) -> Action:
        """Slice step ``step`` out of a policy reply's ``actions`` chunk."""
        return cls(vector=[float(x) for x in reply["actions"][step]])
