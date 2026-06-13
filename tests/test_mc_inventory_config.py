"""T12.1.4 — pibot.mc inventory + config routes (reuse pibot.inventory / pibot.config)."""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app

_AUTH = {"Authorization": "Bearer secret"}


def _run(coro) -> None:
    asyncio.run(coro)


def test_inventory_add_list_rename_remove_roundtrip() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            # add
            r = await c.post(
                "/api/robots",
                json={"alias": "pibot", "ip": "192.168.100.2", "user": "ubuntu"},
                headers=_AUTH,
            )
            assert r.status == 201
            assert (await r.json())["address"] == "192.168.100.2"

            # list
            r = await c.get("/api/robots", headers=_AUTH)
            rows = await r.json()
            assert [x["alias"] for x in rows] == ["pibot"]
            assert rows[0]["user"] == "ubuntu"

            # rename
            r = await c.post("/api/robots/pibot/rename", json={"alias": "bot"}, headers=_AUTH)
            assert r.status == 200
            rows = await (await c.get("/api/robots", headers=_AUTH)).json()
            assert [x["alias"] for x in rows] == ["bot"]

            # remove
            r = await c.delete("/api/robots/bot", headers=_AUTH)
            assert r.status == 200
            rows = await (await c.get("/api/robots", headers=_AUTH)).json()
            assert rows == []

    _run(body())


def test_inventory_remove_unknown_is_404() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            r = await c.delete("/api/robots/nope", headers=_AUTH)
            assert r.status == 404

    _run(body())


def test_config_get_returns_resolved_defaults() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            r = await c.get("/api/config", headers=_AUTH)
            assert r.status == 200
            cfg = await r.json()
            assert cfg["tcp_port"] == 3333  # default
            assert cfg["transport"] == "serial"

    _run(body())


def test_config_post_valid_update_persists() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            r = await c.post("/api/config", json={"tcp_port": 4444}, headers=_AUTH)
            assert r.status == 200
            assert (await r.json())["tcp_port"] == 4444
            # GET reflects the persisted change
            cfg = await (await c.get("/api/config", headers=_AUTH)).json()
            assert cfg["tcp_port"] == 4444

    _run(body())


def test_config_post_rejects_unknown_key() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            r = await c.post("/api/config", json={"nope": 1}, headers=_AUTH)
            assert r.status == 400
            # the rejected edit did not corrupt the config
            cfg = await (await c.get("/api/config", headers=_AUTH)).json()
            assert "nope" not in cfg

    _run(body())


def test_config_post_rejects_wrong_type() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret")
        async with TestClient(TestServer(app)) as c:
            r = await c.post("/api/config", json={"tcp_port": "not-an-int"}, headers=_AUTH)
            assert r.status == 400

    _run(body())
