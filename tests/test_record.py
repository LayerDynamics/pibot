"""T9.5 — demonstration recording: capture obs + teleop action into the episode logger."""

from __future__ import annotations

from pibot.ml.episode_logger import EpisodeLogger
from pibot.ml.pibot_environment import PibotEnvironment
from pibot.ml.record import record_demo_step


class _Cam:
    def capture(self) -> str:
        return "IMG"


def test_record_demo_step_logs_obs_and_teleop_action() -> None:
    env = PibotEnvironment(_Cam(), state_fn=lambda: [0.5, 0.0], prompt="drive to the red ball")
    log = EpisodeLogger(clock=lambda: 0.0)
    log.start_episode("drive to the red ball")

    record_demo_step(env, log, [0.5, 0.0])

    rec = log.records[0]
    assert rec.obs == {
        "image": {"base_0_rgb": "IMG"},
        "state": [0.5, 0.0],
        "prompt": "drive to the red ball",
    }
    assert rec.action == {"actions": [0.5, 0.0]}


def test_record_demo_step_accumulates_frames() -> None:
    env = PibotEnvironment(_Cam(), state_fn=lambda: [0.0, 0.0], prompt="p")
    log = EpisodeLogger(clock=lambda: 0.0)
    log.start_episode("p")
    for v in ([0.1, 0.0], [0.2, 0.0], [0.0, 1.0]):
        record_demo_step(env, log, v)
    assert [r.action["actions"] for r in log.records] == [[0.1, 0.0], [0.2, 0.0], [0.0, 1.0]]
    assert [r.frame for r in log.records] == [0, 1, 2]
