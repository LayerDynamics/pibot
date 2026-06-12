"""``/api/robots`` — inventory CRUD, delegating to ``pibot.inventory`` (SPEC-3 FR-3).

The sidecar owns no inventory state of its own: each call loads/saves the shared
``$PIBOT_CONFIG_DIR/inventory.toml`` so the GUI and the CLI see one inventory.
"""

from __future__ import annotations

from typing import Any

from aiohttp import web

from pibot.errors import InventoryError
from pibot.inventory import Inventory, InventoryRecord


def _record_out(rec: InventoryRecord) -> dict[str, Any]:
    return {
        "alias": rec.alias,
        "address": rec.address,
        "ip": rec.ip,
        "hostname": rec.hostname,
        "user": rec.user,
        "link": rec.link,
        "pi": rec.pi,
    }


async def handle_robots_list(request: web.Request) -> web.Response:
    inv = Inventory.load()
    return web.json_response([_record_out(r) for r in inv.list()])


async def handle_robots_add(request: web.Request) -> web.Response:
    data = await request.json()
    alias = data.get("alias")
    if not alias:
        raise web.HTTPBadRequest(text="alias required")
    inv = Inventory.load()
    rec = InventoryRecord(
        alias=str(alias),
        ip=str(data.get("ip", "")),
        hostname=str(data.get("hostname", "")),
        user=data.get("user"),
        link=str(data.get("link", "")),
    )
    inv.add(rec)
    inv.save()
    return web.json_response(_record_out(rec), status=201)


async def handle_robots_delete(request: web.Request) -> web.Response:
    alias = request.match_info["alias"]
    inv = Inventory.load()
    try:
        inv.remove(alias)
    except InventoryError as exc:
        raise web.HTTPNotFound(text=str(exc)) from exc
    inv.save()
    return web.json_response({"removed": alias})


async def handle_robots_rename(request: web.Request) -> web.Response:
    old = request.match_info["alias"]
    data = await request.json()
    new = data.get("alias")
    if not new:
        raise web.HTTPBadRequest(text="new alias required")
    inv = Inventory.load()
    try:
        inv.set_alias(old, str(new))
    except InventoryError as exc:
        raise web.HTTPNotFound(text=str(exc)) from exc
    inv.save()
    return web.json_response({"alias": new})


def add_inventory_routes(app: web.Application) -> None:
    app.router.add_get("/api/robots", handle_robots_list)
    app.router.add_post("/api/robots", handle_robots_add)
    app.router.add_delete("/api/robots/{alias}", handle_robots_delete)
    app.router.add_post("/api/robots/{alias}/rename", handle_robots_rename)
