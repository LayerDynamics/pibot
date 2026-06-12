"""T8.1 — the observation/action contract types (SPEC-2 Appendix B), numpy-free.

These dataclasses ARE the wire contract between the on-robot client and the policy
server, so they must serialize to exactly the Appendix-B shape. Image data is opaque
(``Any``) so the module imports no numpy — the isolation guard (T7.1) keeps holding.
"""

from __future__ import annotations

from pibot.ml.types import Action, Observation


def test_observation_to_dict_matches_appendix_b() -> None:
    obs = Observation(image="IMG", state=[1.0, 2.0, 3.0], prompt="drive to the red ball")
    d = obs.to_dict()
    assert set(d) == {"image", "state", "prompt"}
    assert d["image"] == {"base_0_rgb": "IMG"}  # default openpi image key
    assert d["state"] == [1.0, 2.0, 3.0]
    assert d["prompt"] == "drive to the red ball"


def test_observation_image_key_is_overridable() -> None:
    obs = Observation(image="IMG", state=[], prompt="p", image_key="cam_high")
    assert obs.to_dict()["image"] == {"cam_high": "IMG"}


def test_observation_state_is_copied_not_aliased() -> None:
    src = [1.0]
    d = Observation(image="x", state=src, prompt="p").to_dict()
    d["state"].append(9.0)
    assert src == [1.0]  # to_dict must copy, not alias the caller's list


def test_action_from_reply_slices_the_step() -> None:
    reply = {"actions": [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]}
    assert Action.from_reply(reply, step=0).vector == [0.1, 0.2]
    assert Action.from_reply(reply, step=1).vector == [0.3, 0.4]


def test_action_from_reply_handles_numpy_like_rows() -> None:
    class _Row:
        def __init__(self, vals: list[float]) -> None:
            self._vals = vals

        def __iter__(self):
            return iter(self._vals)

    reply = {"actions": [_Row([0.7, 0.8])]}
    assert Action.from_reply(reply, step=0).vector == [0.7, 0.8]
