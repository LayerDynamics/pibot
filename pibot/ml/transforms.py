"""Server-side PiBot policy transforms (SPEC-2 §3.2, run on the M4 Max policy server).

``PibotInputs`` packs a PiBot observation into the model's input dict; ``PibotOutputs``
slices the model's wide action chunk down to PiBot's ``[v, ω]`` (``action_dim = 2``, OQ-2)
before it streams to the robot. The UR5 example (PIML §4) is the template; the real
openpi transform pipeline (normalization, tokenization, padding to the model's tensor
shapes) wraps these on the server. The slicing/packing here is pure and works on numpy
arrays *or* nested lists, so it is unit-tested without numpy.
"""

from __future__ import annotations

from typing import Any

# PiBot's action space: [v, ω] (differential drive). Servos excluded from V1 (OQ-2).
ACTION_DIM = 2


def _slice_cols(actions: Any, n: int) -> Any:
    """Keep the first ``n`` columns of an action chunk (numpy array or list of rows)."""
    if hasattr(actions, "shape"):  # numpy array
        return actions[:, :n]
    return [list(row)[:n] for row in actions]


class PibotInputs:
    """Pack a PiBot observation ``{image, state, prompt}`` for the policy model."""

    def __call__(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "image": data.get("image", {}),
            "state": list(data.get("state", [])),
            "prompt": data.get("prompt", ""),
        }


class PibotOutputs:
    """Slice the model's action chunk down to PiBot's ``[v, ω]`` columns."""

    def __call__(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"actions": _slice_cols(data["actions"], ACTION_DIM)}
