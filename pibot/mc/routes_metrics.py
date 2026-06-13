"""T12.4.2 — /api/telemetry/history + /api/telemetry/export.

The ``MetricsStore`` is stored on the app via ``METRICS_STORE``.  The telemetry WS handler
in ``routes_link`` writes every snapshot into the store (the fan-out tee).
"""

from __future__ import annotations

from aiohttp import web

from pibot.mc.metrics import MetricsStore

METRICS_STORE: web.AppKey[MetricsStore] = web.AppKey("pibot_mc_metrics", MetricsStore)


async def handle_history(request: web.Request) -> web.Response:
    """GET /api/telemetry/history?from=<ts>&to=<ts>&fields=ts,temp_c,..."""
    store = request.app[METRICS_STORE]
    try:
        from_ts = float(request.query.get("from", 0))
        to_ts = float(request.query.get("to", 9_999_999_999.0))
    except ValueError:
        raise web.HTTPBadRequest(text="from/to must be numeric UNIX timestamps") from None

    fields_raw = request.query.get("fields")
    fields = [f.strip() for f in fields_raw.split(",")] if fields_raw else None

    rows = store.query(from_ts, to_ts, fields=fields)
    return web.json_response({"rows": rows, "count": len(rows)})


async def handle_export(request: web.Request) -> web.Response:
    """GET /api/telemetry/export?from=<ts>&to=<ts>&fmt=csv|json"""
    store = request.app[METRICS_STORE]
    try:
        from_ts = float(request.query.get("from", 0))
        to_ts = float(request.query.get("to", 9_999_999_999.0))
    except ValueError:
        raise web.HTTPBadRequest(text="from/to must be numeric UNIX timestamps") from None

    fmt = request.query.get("fmt", "json").lower()
    if fmt not in ("csv", "json"):
        raise web.HTTPBadRequest(text="fmt must be csv or json")

    data = store.export(from_ts, to_ts, fmt=fmt)
    if fmt == "csv":
        return web.Response(
            text=data,
            content_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="telemetry.csv"'},
        )
    return web.Response(text=data, content_type="application/json")


async def handle_prune(request: web.Request) -> web.Response:
    """POST /api/telemetry/prune — manual retention enforcement."""
    store = request.app[METRICS_STORE]
    deleted = store.prune()
    return web.json_response({"deleted": deleted})


def add_metrics_routes(
    app: web.Application,
    *,
    metrics_store: MetricsStore | None = None,
) -> None:
    store = metrics_store or MetricsStore()
    app[METRICS_STORE] = store
    app.router.add_get("/api/telemetry/history", handle_history)
    app.router.add_get("/api/telemetry/export", handle_export)
    app.router.add_post("/api/telemetry/prune", handle_prune)
