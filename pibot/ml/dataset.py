"""Demonstration episodes -> LeRobot dataset frames (SPEC-2 / M9 T9.2).

:func:`to_frames` turns the episode logger's records into the per-frame rows a LeRobot
dataset expects (``observation.image`` / ``observation.state`` / ``action`` + episode and
frame indices + timestamp + task prompt) — pure and numpy-free so it is unit-tested. The
actual on-disk ``LeRobotDataset`` write (parquet + encoded video) is openpi/lerobot glue
run on the M4 Max, where those deps live.
"""

from __future__ import annotations

from typing import Any

from pibot.ml.episode_logger import StepRecord


def _action_vector(action: Any) -> list[float]:
    vec = action.get("actions") if isinstance(action, dict) else action
    return list(vec) if vec is not None else []


def to_frames(episodes: list[list[StepRecord]]) -> list[dict[str, Any]]:
    """Flatten recorded episodes into LeRobot per-frame rows."""
    frames: list[dict[str, Any]] = []
    for ep_idx, episode in enumerate(episodes):
        for fr_idx, rec in enumerate(episode):
            obs = rec.obs or {}
            image = obs.get("image", {})
            frames.append(
                {
                    "observation.image": image.get("base_0_rgb")
                    if isinstance(image, dict)
                    else None,
                    "observation.state": list(obs.get("state", [])),
                    "action": _action_vector(rec.action),
                    "episode_index": ep_idx,
                    "frame_index": fr_idx,
                    "timestamp": rec.ts,
                    "task": obs.get("prompt", rec.prompt),
                }
            )
    return frames


def write_dataset(  # pragma: no cover - LeRobot on-disk write (lerobot dep, M4 Max)
    episodes: list[list[StepRecord]], out_dir: str, repo_id: str, fps: int = 20
) -> str:
    """Write the episodes to a LeRobot dataset on disk; return the dataset path."""
    from lerobot.common.datasets.lerobot_dataset import LeRobotDataset

    features = {
        "observation.image": {
            "dtype": "video",
            "shape": (224, 224, 3),
            "names": ["height", "width", "channels"],
        },
        "observation.state": {
            "dtype": "float32",
            "shape": (2,),
            "names": ["v", "w"],
        },
        "action": {
            "dtype": "float32",
            "shape": (2,),
            "names": ["v", "w"],
        },
    }
    ds = LeRobotDataset.create(repo_id=repo_id, fps=fps, root=out_dir, features=features)
    for episode in episodes:
        for rec in episode:
            obs = rec.obs or {}
            ds.add_frame(
                {
                    "observation.image": obs.get("image", {}).get("base_0_rgb"),
                    "observation.state": obs.get("state", []),
                    "action": _action_vector(rec.action),
                    "task": obs.get("prompt", rec.prompt),
                }
            )
        ds.save_episode()
    return out_dir
