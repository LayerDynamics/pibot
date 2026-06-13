"""T12.4.2 — /api/telemetry/history + /api/telemetry/export + fan-out tee."""

from __future__ import annotations

import asyncio
import csv
import io
import time
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.metrics import MetricsStore

_AUTH = {"Authorization": "Bearer secret"}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _snap(ts: float, temp: float = 42.0) -> dict:
    return {
        "ts": ts,
        "pi": {"temp_c": temp},
        "safety": {"estop": False},
        "transport": {"open": True},
        "policy": {"connected": True, "last_inference_ms": 10.0, "chunk_age_ms": 30.0},
        "robot": {"battery": {"volts": 3.7}},
    }


# ---------------------------------------------------------------------------
# /api/telemetry/history
# ---------------------------------------------------------------------------


def test_history_returns_empty_before_writes() -> None:
    async def body() -> None:
        store = MetricsStore(":memory:")
        app = create_mc_app(token="secret", metrics_store=store)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(
                "/api/telemetry/history",
                params={"from": "0", "to": "9999999999"},
                headers=_AUTH,
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["count"] == 0
            assert data["rows"] == []

    _run(body())


def test_history_returns_rows_in_window() -> None:
    async def body() -> None:
        store = MetricsStore(":memory:", flush_size=1)
        base = 1_000_000.0
        for i in range(10):
            store.write(_snap(base + i))

        app = create_mc_app(token="secret", metrics_store=store)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(
                "/api/telemetry/history",
                params={"from": str(base + 3), "to": str(base + 6)},
                headers=_AUTH,
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["count"] == 4
            for row in data["rows"]:
                assert base + 3 <= row["ts"] <= base + 6

    _run(body())


def test_history_field_selection() -> None:
    async def body() -> None:
        store = MetricsStore(":memory:", flush_size=1)
        base = 2_000_000.0
        store.write(_snap(base))

        app = create_mc_app(token="secret", metrics_store=store)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(
                "/api/telemetry/history",
                params={"from": str(base - 1), "to": str(base + 1), "fields": "ts,temp_c"},
                headers=_AUTH,
            )
            assert resp.status == 200
            data = await resp.json()
            assert len(data["rows"]) == 1
            assert set(data["rows"][0].keys()) == {"ts", "temp_c"}

    _run(body())


def test_history_bad_timestamp_returns_400() -> None:
    async def body() -> None:
        store = MetricsStore(":memory:")
        app = create_mc_app(token="secret", metrics_store=store)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(
                "/api/telemetry/history",
                params={"from": "not-a-number"},
                headers=_AUTH,
            )
            assert resp.status == 400

    _run(body())


# ---------------------------------------------------------------------------
# /api/telemetry/export
# ---------------------------------------------------------------------------


def test_export_json() -> None:
    async def body() -> None:
        store = MetricsStore(":memory:", flush_size=1)
        base = 3_000_000.0
        store.write(_snap(base, temp=30.0))
        store.write(_snap(base + 1, temp=31.0))

        app = create_mc_app(token="secret", metrics_store=store)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(
                "/api/telemetry/export",
                params={"from": str(base - 1), "to": str(base + 5), "fmt": "json"},
                headers=_AUTH,
            )
            assert resp.status == 200
            assert "application/json" in resp.content_type
            rows = await resp.json()
            assert isinstance(rows, list)
            assert len(rows) == 2

    _run(body())


def test_export_csv() -> None:
    async def body() -> None:
        store = MetricsStore(":memory:", flush_size=1)
        base = 4_000_000.0
        store.write(_snap(base, temp=22.0))

        app = create_mc_app(token="secret", metrics_store=store)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(
                "/api/telemetry/export",
                params={"from": str(base - 1), "to": str(base + 1), "fmt": "csv"},
                headers=_AUTH,
            )
            assert resp.status == 200
            assert "text/csv" in resp.content_type
            body_text = await resp.text()
            rows = list(csv.DictReader(io.StringIO(body_text)))
            assert len(rows) == 1
            assert float(rows[0]["temp_c"]) == pytest.approx(22.0)

    _run(body())


def test_export_bad_fmt_returns_400() -> None:
    async def body() -> None:
        store = MetricsStore(":memory:")
        app = create_mc_app(token="secret", metrics_store=store)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(
                "/api/telemetry/export",
                params={"fmt": "xml"},
                headers=_AUTH,
            )
            assert resp.status == 400

    _run(body())


# ---------------------------------------------------------------------------
# /api/telemetry/prune
# ---------------------------------------------------------------------------


def test_prune_endpoint() -> None:
    async def body() -> None:
        store = MetricsStore(":memory:", flush_size=1)
        now = time.time()
        old_ts = now - 40 * 86400  # older than MAX_AGE_DAYS
        store.write(_snap(old_ts))
        store.write(_snap(now))

        app = create_mc_app(token="secret", metrics_store=store)
        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/telemetry/prune", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["deleted"] >= 1
        assert store.count() == 1

    _run(body())
