"""Episode logger — an openpi ``Runtime`` subscriber that records demonstrations.

Each control step's ``on_step(observation, action)`` is appended as a :class:`StepRecord`
into the current episode (one episode per recorded run, tagged with the task prompt). The
LeRobot dataset writer (T9.2) turns these records into a fine-tuning dataset. The clock is
injected for deterministic timestamps; image data is opaque so this module needs no numpy.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StepRecord:
    obs: dict[str, Any] | None
    action: dict[str, Any]
    ts: float
    episode: int
    frame: int
    prompt: str


class EpisodeLogger:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._records: list[StepRecord] = []
        self._episode = -1
        self._frame = 0
        self._prompt = ""

    def start_episode(self, prompt: str = "") -> None:
        self._episode += 1
        self._frame = 0
        self._prompt = prompt

    def on_step(self, obs: dict[str, Any] | None, action: dict[str, Any]) -> None:
        if self._episode < 0:
            self.start_episode()  # auto-start episode 0 if the caller didn't
        self._records.append(
            StepRecord(obs, action, self._clock(), self._episode, self._frame, self._prompt)
        )
        self._frame += 1

    def end_episode(self) -> None:
        # boundary marker; the next start_episode() increments the episode index
        self._prompt = ""

    @property
    def records(self) -> list[StepRecord]:
        return list(self._records)

    def episodes(self) -> list[list[StepRecord]]:
        """The records grouped into per-episode lists, in order."""
        grouped: list[list[StepRecord]] = []
        for rec in self._records:
            while rec.episode >= len(grouped):
                grouped.append([])
            grouped[rec.episode].append(rec)
        return grouped
