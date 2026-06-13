"""T12.4.2 — /api/telemetry/history + /api/telemetry/export routes.

Exercises the HTTP layer over a real in-memory MetricsStore.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.metrics import MetricsStore
from pibot.mc.state import McState

_AUTH = {"Authorization": "Bearer secret"}


def _store_with_rows(rows: list[dict[str, Any]]) -> MetricsStore:
    store = MetricsStore()
    for row in rows:
        store.write(row)
    store.flush()
    return store


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _snap(ts: float, temp: float = 25.0, batt: float = 12.0) -> dict:
    return {"pi": {"temp_c": temp, "battery_v": batt}, "ts": ts}


# ---------------------------------------------------------------------------


def test_history_returns_all_rows() -> None:
    async def body() -> None:
        store = _store_with_rows([_snap(1000.0), _snap(2000.0), _snap(3000.0)])
        app = create_mc_app(state=McState(token="secret"), metrics_store=store)
        async with TestClient(TestServer(app)) as c:
            resp = await c.get("/api/telemetry/history", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["count"] == 3
            assert len(data["rows"]) == 3

    _run(body())


def test_history_filters_by_time_range() -> None:
    async def body() -> None:
        store = _store_with_rows([_snap(1000.0), _snap(5000.0), _snap(9000.0)])
        app = create_mc_app(state=McState(token="secret"), metrics_store=store)
        async with TestClient(TestServer(app)) as c:
            resp = await c.get(
                "/api/telemetry/history",
                params={"from": "4000", "to": "6000"},
                headers=_AUTH,
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["count"] == 1
            assert data["rows"][0]["ts"] == pytest.approx(5000.0)

    _run(body())


def test_history_field_projection() -> None:
    async def body() -> None:
        store = _store_with_rows([_snap(1000.0, temp=42.0)])
        app = create_mc_app(state=McState(token="secret"), metrics_store=store)
        async with TestClient(TestServer(app)) as c:
            resp = await c.get(
                "/api/telemetry/history",
                params={"fields": "ts,temp_c"},
                headers=_AUTH,
            )
            assert resp.status == 200
            data = await resp.json()
            row = data["rows"][0]
            assert "ts" in row
            assert "temp_c" in row
            assert "battery_v" not in row

    _run(body())


def test_history_bad_timestamp_returns_400() -> None:
    async def body() -> None:
        app = create_mc_app(state=McState(token="secret"))
        async with TestClient(TestServer(app)) as c:
            resp = await c.get(
                "/api/telemetry/history",
                params={"from": "not-a-number"},
                headers=_AUTH,
            )
            assert resp.status == 400

    _run(body())


def test_export_json() -> None:
    async def body() -> None:
        store = _store_with_rows([_snap(1000.0, temp=30.0), _snap(2000.0, temp=31.0)])
        app = create_mc_app(state=McState(token="secret"), metrics_store=store)
        async with TestClient(TestServer(app)) as c:
            resp = await c.get(
                "/api/telemetry/export",
                params={"fmt": "json"},
                headers=_AUTH,
            )
            assert resp.status == 200
            assert resp.content_type == "application/json"
            body_text = await resp.text()
            parsed = json.loads(body_text)
            assert isinstance(parsed, (list, dict))

    _run(body())


def test_export_csv() -> None:
    async def body() -> None:
        store = _store_with_rows([_snap(1000.0), _snap(2000.0)])
        app = create_mc_app(state=McState(token="secret"), metrics_store=store)
        async with TestClient(TestServer(app)) as c:
            resp = await c.get(
                "/api/telemetry/export",
                params={"fmt": "csv"},
                headers=_AUTH,
            )
            assert resp.status == 200
            assert "text/csv" in resp.content_type
            text = await resp.text()
            lines = [ln for ln in text.splitlines() if ln.strip()]
            assert len(lines) >= 3  # header + 2 data rows

    _run(body())


def test_export_bad_fmt_returns_400() -> None:
    async def body() -> None:
        app = create_mc_app(state=McState(token="secret"))
        async with TestClient(TestServer(app)) as c:
            resp = await c.get(
                "/api/telemetry/export",
                params={"fmt": "xml"},
                headers=_AUTH,
            )
            assert resp.status == 400

    _run(body())


def test_prune_route() -> None:
    async def body() -> None:
        old_ts = time.time() - 40 * 86400  # 40 days ago
        store = _store_with_rows([_snap(old_ts), _snap(time.time())])
        app = create_mc_app(state=McState(token="secret"), metrics_store=store)
        async with TestClient(TestServer(app)) as c:
            resp = await c.post("/api/telemetry/prune", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert "deleted" in data
            assert data["deleted"] >= 1

    _run(body())
