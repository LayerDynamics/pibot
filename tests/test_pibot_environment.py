"""T8.3 — PibotEnvironment.get_observation: assemble the Appendix-B obs from camera+state.

Duck-types openpi's Environment ABC (reset / is_episode_complete / get_observation /
apply_action). apply_action is intentionally unimplemented until M10 (closed loop) — the
open-loop env (T8.4) overrides it; that's a documented gate, not a silent stub.
"""

from __future__ import annotations

import pytest

from pibot.ml.pibot_environment import PibotEnvironment


class _FakeCamera:
    def __init__(self, img: object) -> None:
        self._img = img

    def capture(self) -> object:
        return self._img


def test_get_observation_assembles_appendix_b() -> None:
    env = PibotEnvironment(
        _FakeCamera("IMG"), state_fn=lambda: [0.1, 0.2, 0.3], prompt="drive to the red ball"
    )
    obs = env.get_observation()
    assert obs == {
        "image": {"base_0_rgb": "IMG"},
        "state": [0.1, 0.2, 0.3],
        "prompt": "drive to the red ball",
    }


def test_reset_issues_a_stop() -> None:
    stops: list[int] = []
    env = PibotEnvironment(_FakeCamera("x"), lambda: [], "", stop_fn=lambda: stops.append(1))
    env.reset()
    assert stops == [1]


def test_is_episode_complete_is_false_for_continuous_driving() -> None:
    env = PibotEnvironment(_FakeCamera("x"), lambda: [], "")
    assert env.is_episode_complete() is False


def test_apply_action_is_gated_until_m10() -> None:
    env = PibotEnvironment(_FakeCamera("x"), lambda: [], "")
    with pytest.raises(NotImplementedError, match="M10"):
        env.apply_action({"actions": [[0.0, 0.0]]})
