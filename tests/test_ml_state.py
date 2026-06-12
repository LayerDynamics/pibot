"""OQ-2 — the rover's proprioceptive state vector: the last commanded velocity [v, ω]."""

from __future__ import annotations

from pibot.ml.state import VelocityState


def test_defaults_to_zero_velocity() -> None:
    assert VelocityState().vector() == [0.0, 0.0]


def test_update_from_per_step_action_dict() -> None:
    vs = VelocityState()
    vs.update({"actions": [0.5, -0.3]})
    assert vs.vector() == [0.5, -0.3]


def test_update_from_raw_vector_ignores_extra_dims() -> None:
    vs = VelocityState()
    vs.update([0.2, 0.1, 99.0])  # e.g. a future [v, w, servo] — only v,w are state
    assert vs.vector() == [0.2, 0.1]


def test_update_ignores_malformed_short_vector() -> None:
    vs = VelocityState()
    vs.update({"actions": [0.5]})  # malformed; keep the prior velocity
    assert vs.vector() == [0.0, 0.0]
