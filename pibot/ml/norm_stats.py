"""Normalization statistics for PiBot's [v, ω] state + action (SPEC-2 / M9 T9.4).

The policy server normalizes observations/actions by these per-dimension mean/std before
the model sees them (and de-normalizes the output). Computed over the demonstration
dataset; pure-Python (numpy-free) so it is unit-tested and the stats file is plain JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _mean_std(vectors: list[list[float]]) -> dict[str, list[float]]:
    if not vectors:
        return {"mean": [], "std": []}
    dim = len(vectors[0])
    n = len(vectors)
    mean = [sum(v[i] for v in vectors) / n for i in range(dim)]
    std = [(sum((v[i] - mean[i]) ** 2 for v in vectors) / n) ** 0.5 for i in range(dim)]
    return {"mean": mean, "std": std}


def compute(frames: list[dict[str, Any]]) -> dict[str, dict[str, list[float]]]:
    """Per-dimension mean/std of ``observation.state`` and ``action`` over the frames."""
    states = [list(f["observation.state"]) for f in frames if f.get("observation.state")]
    actions = [list(f["action"]) for f in frames if f.get("action")]
    return {"state": _mean_std(states), "action": _mean_std(actions)}


def save(stats: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(stats, indent=2), encoding="utf-8")


def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
