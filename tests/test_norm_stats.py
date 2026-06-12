"""T9.4 — normalization stats (mean/std) for the [v, ω] state + action over a dataset."""

from __future__ import annotations

from pibot.ml import norm_stats


def test_compute_mean_and_std_per_dimension() -> None:
    frames = [
        {"observation.state": [0.0, 0.0], "action": [1.0, 1.0]},
        {"observation.state": [2.0, 4.0], "action": [3.0, 5.0]},
    ]
    stats = norm_stats.compute(frames)
    assert stats["state"]["mean"] == [1.0, 2.0]
    assert stats["state"]["std"] == [1.0, 2.0]  # |0-1|,|2-1|=1 ; |0-2|,|4-2|=2
    assert stats["action"]["mean"] == [2.0, 3.0]
    assert stats["action"]["std"] == [1.0, 2.0]


def test_empty_frames_give_empty_stats() -> None:
    stats = norm_stats.compute([])
    assert stats["state"] == {"mean": [], "std": []}
    assert stats["action"] == {"mean": [], "std": []}


def test_save_and_load_round_trip(tmp_path) -> None:
    stats = {
        "state": {"mean": [1.0, 2.0], "std": [0.5, 0.5]},
        "action": {"mean": [0.0, 0.0], "std": [1.0, 1.0]},
    }
    path = tmp_path / "norm_stats.json"
    norm_stats.save(stats, path)
    assert norm_stats.load(path) == stats
