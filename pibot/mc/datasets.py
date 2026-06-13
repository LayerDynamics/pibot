"""T12.4.5 — Read-only episode index over recorded demonstrations (SPEC-2 path).

``EpisodeIndex`` accumulates episode metadata from finalized ``EpisodeLogger`` runs.
It never mutates the dataset; the recording path in ``routes_record`` is the only writer.

In production the index is populated by the post-write hook in ``routes_record``.
In tests an ``EpisodeIndex`` is constructed and pre-populated directly.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any

from pibot.ml.dataset import to_frames
from pibot.ml.episode_logger import StepRecord


@dataclasses.dataclass
class EpisodeMeta:
    id: str
    task: str
    length: int
    started: float
    ended: float

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class EpisodeIndex:
    """In-memory read-only index of recorded demonstration episodes."""

    def __init__(self) -> None:
        self._episodes: list[EpisodeMeta] = []
        self._frames: dict[str, list[dict[str, Any]]] = {}

    def add_episodes(
        self,
        episodes: list[list[StepRecord]],
        *,
        task: str = "",
    ) -> list[str]:
        """Register a set of newly recorded episodes. Returns the assigned ids."""
        ids = []
        for ep in episodes:
            if not ep:
                continue
            ep_id = f"ep_{len(self._episodes):06d}"
            started = ep[0].ts if ep else time.time()
            ended = ep[-1].ts if ep else started
            prompt = ep[0].prompt if ep else task
            meta = EpisodeMeta(
                id=ep_id,
                task=prompt or task,
                length=len(ep),
                started=started,
                ended=ended,
            )
            self._episodes.append(meta)
            # flatten to frames for per-episode detail (read-only browse)
            self._frames[ep_id] = to_frames([ep])
            ids.append(ep_id)
        return ids

    def list_episodes(self) -> list[dict[str, Any]]:
        return [m.as_dict() for m in self._episodes]

    def get_episode(self, ep_id: str) -> dict[str, Any] | None:
        meta = next((m for m in self._episodes if m.id == ep_id), None)
        if meta is None:
            return None
        frames = self._frames.get(ep_id, [])
        return {
            **meta.as_dict(),
            "frames": list(frames),  # copy so callers can't mutate internal state
        }

    def __len__(self) -> int:
        return len(self._episodes)
