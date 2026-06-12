"""``/api/config`` — read/edit the suite config with the SAME validation as the CLI.

POST validates by merging the updates into ``config.toml`` and reloading through
``pibot.config.load_config`` — so an unknown key or wrong-typed value is rejected with the
exact ``ConfigError`` rules the CLI enforces (SPEC-3 FR-4). The prior file is restored if
validation fails, so a bad POST never corrupts the stored config.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from aiohttp import web

from pibot import tomlio
from pibot.config import config_dir, load_config
from pibot.errors import ConfigError


async def handle_config_get(request: web.Request) -> web.Response:
    return web.json_response(asdict(load_config()))


async def handle_config_post(request: web.Request) -> web.Response:
    updates = await request.json()
    if not isinstance(updates, dict):
        raise web.HTTPBadRequest(text="expected a JSON object of config keys")

    path = config_dir() / "config.toml"
    backup: str | None = path.read_text(encoding="utf-8") if path.exists() else None
    existing: dict[str, Any] = tomlio.load(path)
    merged = {**existing, **updates}

    path.parent.mkdir(parents=True, exist_ok=True)
    tomlio.dump(merged, path)
    try:
        cfg = load_config(path)
    except ConfigError as exc:
        # Roll back to the prior state — a rejected edit must not corrupt the config.
        if backup is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(backup, encoding="utf-8")
        raise web.HTTPBadRequest(text=str(exc)) from exc
    return web.json_response(asdict(cfg))


def add_config_routes(app: web.Application) -> None:
    app.router.add_get("/api/config", handle_config_get)
    app.router.add_post("/api/config", handle_config_post)
