"""T9.1 — the episode logger: an openpi Runtime subscriber recording (obs, action, ts).

Records every control step into bounded episodes (one per recorded run, tagged with the
task prompt) — the raw material the LeRobot dataset writer (T9.2) converts for fine-tuning.
Injected clock keeps timestamps deterministic; image data stays opaque (numpy-free).
"""

from __future__ import annotations

from pibot.ml.episode_logger import EpisodeLogger


def test_on_step_records_frames_and_timestamps_in_order() -> None:
    ticks = iter([1.0, 2.0])
    log = EpisodeLogger(clock=lambda: next(ticks))
    log.start_episode("drive to the red ball")
    log.on_step({"prompt": "drive to the red ball"}, {"actions": [0.5, 0.0]})
    log.on_step({"prompt": "drive to the red ball"}, {"actions": [0.6, 0.1]})

    recs = log.records
    assert len(recs) == 2
    assert recs[0].episode == 0 and recs[0].frame == 0 and recs[0].ts == 1.0
    assert recs[1].frame == 1 and recs[1].ts == 2.0
    assert recs[0].action == {"actions": [0.5, 0.0]}
    assert recs[0].prompt == "drive to the red ball"


def test_episode_index_increments_and_frame_resets() -> None:
    log = EpisodeLogger(clock=lambda: 0.0)
    log.start_episode("a")
    log.on_step({}, {"actions": []})
    log.end_episode()
    log.start_episode("b")
    log.on_step({}, {"actions": []})

    recs = log.records
    assert recs[0].episode == 0 and recs[1].episode == 1
    assert recs[1].frame == 0  # frame resets per episode
    assert recs[1].prompt == "b"


def test_on_step_auto_starts_episode_zero() -> None:
    log = EpisodeLogger(clock=lambda: 0.0)
    log.on_step({}, {"actions": []})  # no explicit start_episode()
    assert log.records[0].episode == 0


def test_episodes_groups_records_by_episode() -> None:
    log = EpisodeLogger(clock=lambda: 0.0)
    log.start_episode("a")
    log.on_step({}, {"actions": [1.0]})
    log.start_episode("b")
    log.on_step({}, {"actions": [2.0]})
    log.on_step({}, {"actions": [3.0]})

    eps = log.episodes()
    assert len(eps) == 2
    assert len(eps[0]) == 1 and len(eps[1]) == 2
