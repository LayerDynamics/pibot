"""T7.5 — the pipe-check latency probe (openpi websocket round-trip timing).

Tested against a FAKE policy (canned chunk) so there's no real network/openpi/numpy in
the unit test; the real WebsocketClientPolicy + random observation are built lazily and
only on a live run.
"""

from __future__ import annotations

from pibot.ml import pipe_check


class _FakeListPolicy:
    """Returns a 50×32 chunk as nested lists (numpy-free)."""

    def __init__(self) -> None:
        self.calls = 0

    def infer(self, obs: dict) -> dict:
        self.calls += 1
        return {"actions": [[0.0] * 32 for _ in range(50)]}


def test_measure_reports_latency_stats_and_chunk_shape() -> None:
    p = _FakeListPolicy()
    stats = pipe_check.measure(p, obs={}, rounds=10)
    assert stats["rounds"] == 10 and p.calls == 10
    assert stats["chunk_shape"] == (50, 32)
    for k in ("min_ms", "median_ms", "p95_ms"):
        assert stats[k] >= 0.0


def test_measure_handles_numpy_like_shape() -> None:
    class _Arr:
        shape = (50, 32)

    class _P:
        def infer(self, obs: dict) -> dict:
            return {"actions": _Arr()}

    stats = pipe_check.measure(_P(), obs={}, rounds=3)
    assert stats["chunk_shape"] == (50, 32)


def test_main_returns_zero_on_reachable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(pipe_check, "_build_policy", lambda **kw: _FakeListPolicy())
    monkeypatch.setattr(pipe_check, "_random_obs", lambda: {})
    rc = pipe_check.main(["--host", "192.168.100.1", "--port", "8000", "--rounds", "5"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "p95" in out and "(50, 32)" in out


def test_main_returns_nonzero_when_unreachable(monkeypatch) -> None:
    def boom(**kw):
        raise OSError("connection refused")

    monkeypatch.setattr(pipe_check, "_build_policy", boom)
    rc = pipe_check.main(["--host", "10.255.255.1", "--port", "8000"])
    assert rc != 0
