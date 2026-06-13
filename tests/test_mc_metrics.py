"""T12.4.1 — MetricsStore: SQLite time-series write / query / export / retention."""

from __future__ import annotations

import json
import time

import pytest

from pibot.mc.metrics import MAX_AGE_DAYS, MetricsStore


def _snap(ts: float, temp: float = 42.0, connected: bool = True) -> dict:
    return {
        "ts": ts,
        "pi": {"temp_c": temp},
        "safety": {"estop": False},
        "transport": {"open": True},
        "policy": {
            "connected": connected,
            "last_inference_ms": 12.5,
            "chunk_age_ms": 50.0,
        },
        "robot": {"battery": {"volts": 3.7}},
    }


@pytest.fixture()
def store() -> MetricsStore:
    s = MetricsStore(":memory:", flush_size=10)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# Write + query
# ---------------------------------------------------------------------------


def test_write_1000_and_query_window(store: MetricsStore) -> None:
    base = 1_000_000.0
    for i in range(1000):
        store.write(_snap(base + i))

    store.flush()
    assert store.count() == 1000

    # query the middle 500 rows
    rows = store.query(base + 200, base + 699)
    assert len(rows) == 500
    assert all(base + 200 <= r["ts"] <= base + 699 for r in rows)
    # ordered ascending
    tss = [r["ts"] for r in rows]
    assert tss == sorted(tss)


def test_query_field_selection(store: MetricsStore) -> None:
    base = 2_000_000.0
    store.write(_snap(base + 0))
    store.write(_snap(base + 1))
    store.flush()

    rows = store.query(base, base + 5, fields=["ts", "temp_c"])
    assert len(rows) == 2
    assert set(rows[0].keys()) == {"ts", "temp_c"}


def test_write_maps_snapshot_fields(store: MetricsStore) -> None:
    ts = 3_000_000.0
    store.write(_snap(ts, temp=55.0), robot="testbot")
    store.flush()

    rows = store.query(ts - 1, ts + 1)
    assert len(rows) == 1
    r = rows[0]
    assert r["temp_c"] == pytest.approx(55.0)
    assert r["estop"] == 0
    assert r["transport_open"] == 1
    assert r["policy_connected"] == 1
    assert r["last_infer_ms"] == pytest.approx(12.5)
    assert r["chunk_age_ms"] == pytest.approx(50.0)
    assert r["robot"] == "testbot"
    # raw is JSON-decodable
    raw = json.loads(r["raw"])
    assert raw["pi"]["temp_c"] == pytest.approx(55.0)


# ---------------------------------------------------------------------------
# Retention / prune
# ---------------------------------------------------------------------------


def test_retention_prunes_old_rows(store: MetricsStore) -> None:
    now = time.time()
    old_ts = now - (MAX_AGE_DAYS + 1) * 86400  # older than the cutoff
    for i in range(20):
        store.write(_snap(old_ts + i))
    for i in range(10):
        store.write(_snap(now + i))
    store.flush()
    assert store.count() == 30

    deleted = store.prune()
    assert deleted >= 20
    remaining = store.count()
    assert remaining == 10


def test_max_rows_prune(store: MetricsStore) -> None:
    """When total rows exceed MAX_ROWS, prune() removes the excess oldest rows."""
    # Override MAX_ROWS via a fresh store with a very small cap.
    import pibot.mc.metrics as metrics_mod

    original = metrics_mod.MAX_ROWS
    metrics_mod.MAX_ROWS = 50
    try:
        s = MetricsStore(":memory:", flush_size=5)
        now = time.time()
        for i in range(80):
            s.write(_snap(now + i))
        s.flush()
        assert s.count() == 80
        deleted = s.prune()
        assert deleted >= 30
        assert s.count() <= 50
        s.close()
    finally:
        metrics_mod.MAX_ROWS = original


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_json(store: MetricsStore) -> None:
    base = 4_000_000.0
    store.write(_snap(base))
    store.write(_snap(base + 1))
    store.flush()

    out = store.export(base - 1, base + 2, fmt="json")
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["ts"] == pytest.approx(base)


def test_export_csv_round_trip(store: MetricsStore) -> None:
    import csv
    import io

    base = 5_000_000.0
    store.write(_snap(base, temp=30.0))
    store.write(_snap(base + 1, temp=31.0))
    store.flush()

    csv_str = store.export(base - 1, base + 5, fmt="csv")
    assert csv_str != ""
    reader = csv.DictReader(io.StringIO(csv_str))
    rows = list(reader)
    assert len(rows) == 2
    assert float(rows[0]["temp_c"]) == pytest.approx(30.0)
    assert float(rows[1]["temp_c"]) == pytest.approx(31.0)


def test_export_csv_empty_returns_empty_string(store: MetricsStore) -> None:
    out = store.export(9_000_000.0, 9_000_001.0, fmt="csv")
    assert out == ""


# ---------------------------------------------------------------------------
# Writer non-blocking (buffer accumulates before flush)
# ---------------------------------------------------------------------------


def test_writer_is_non_blocking(store: MetricsStore) -> None:
    """Rows under flush_size remain in buffer — count() returns 0 before flush."""
    # flush_size=10 → 9 writes should stay buffered
    base = 6_000_000.0
    for i in range(9):
        store.write(_snap(base + i))

    # Without explicit flush, the DB should still be empty.
    # (MetricsStore._flush is triggered at flush_size, not yet reached)
    raw_count = store._conn.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]
    assert raw_count == 0, "rows should still be buffered, not yet written to SQLite"

    # After flush, all rows appear.
    store.flush()
    assert store.count() == 9
