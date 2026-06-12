"""T9.2 — episodes -> LeRobot-format frames (the fine-tuning dataset rows).

The row-schema generation is pure and numpy-free (image opaque); the on-disk LeRobotDataset
write is openpi/lerobot glue exercised on the M4 Max.
"""

from __future__ import annotations

from pibot.ml.dataset import to_frames
from pibot.ml.episode_logger import StepRecord


def _rec(
    ep: int, fr: int, state: list[float], action: list[float], prompt: str = "drive"
) -> StepRecord:
    return StepRecord(
        obs={"image": {"base_0_rgb": "IMG"}, "state": state, "prompt": prompt},
        action={"actions": action},
        ts=float(fr),
        episode=ep,
        frame=fr,
        prompt=prompt,
    )


def test_to_frames_has_lerobot_schema_and_indexing() -> None:
    episodes = [
        [_rec(0, 0, [0.5, 0.0], [0.5, 0.0]), _rec(0, 1, [0.6, 0.0], [0.6, 0.0])],
        [_rec(1, 0, [0.0, 1.0], [0.0, 1.0], prompt="follow me")],
    ]
    frames = to_frames(episodes)
    assert len(frames) == 3
    f0 = frames[0]
    assert {
        "observation.image",
        "observation.state",
        "action",
        "episode_index",
        "frame_index",
        "timestamp",
        "task",
    } <= set(f0)
    assert f0["episode_index"] == 0 and f0["frame_index"] == 0
    assert f0["observation.image"] == "IMG"
    assert f0["observation.state"] == [0.5, 0.0]
    assert f0["action"] == [0.5, 0.0]
    assert f0["task"] == "drive"
    # second episode indexes independently
    assert frames[2]["episode_index"] == 1 and frames[2]["frame_index"] == 0
    assert frames[2]["task"] == "follow me"


def test_to_frames_tolerates_missing_obs() -> None:
    rec = StepRecord(
        obs=None, action={"actions": [0.1, 0.2]}, ts=0.0, episode=0, frame=0, prompt="p"
    )
    frames = to_frames([[rec]])
    assert frames[0]["observation.image"] is None
    assert frames[0]["observation.state"] == []
    assert frames[0]["action"] == [0.1, 0.2]
