"""T12.4.4 — /api/record: demonstration recording via SPEC-2 EpisodeLogger."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app

_AUTH = {"Authorization": "Bearer secret"}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _fake_write_fn(episodes: list[list[Any]], out_dir: str, repo_id: str) -> str:
    """Fake dataset writer that records its arguments for assertion."""
    _fake_write_fn.calls.append(  # type: ignore[attr-defined]
        {"episodes": episodes, "out_dir": out_dir, "repo_id": repo_id}
    )
    return f"{out_dir}/{repo_id}"


_fake_write_fn.calls: list[dict] = []  # type: ignore[attr-defined]


def _app() -> Any:
    _fake_write_fn.calls.clear()
    return create_mc_app(token="secret", record_write_fn=_fake_write_fn)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_record_idle() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            resp = await client.get("/api/record", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["recording"] is False
            assert data["frames"] == 0

    _run(body())


def test_post_record_starts_episode() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            resp = await client.post(
                "/api/record",
                json={"prompt": "pick up the cube", "out_dir": "/tmp/demo"},
                headers=_AUTH,
            )
            assert resp.status == 201
            data = await resp.json()
            assert data["recording"] is True
            assert data["prompt"] == "pick up the cube"

    _run(body())


def test_post_record_requires_out_dir() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            resp = await client.post(
                "/api/record",
                json={"prompt": "test"},
                headers=_AUTH,
            )
            assert resp.status == 400

    _run(body())


def test_post_record_conflict_if_already_active() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            await client.post(
                "/api/record",
                json={"prompt": "demo", "out_dir": "/tmp/demo"},
                headers=_AUTH,
            )
            resp = await client.post(
                "/api/record",
                json={"prompt": "demo2", "out_dir": "/tmp/demo"},
                headers=_AUTH,
            )
            assert resp.status == 409

    _run(body())


def test_post_step_appends_frame() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            await client.post(
                "/api/record",
                json={"prompt": "follow me", "out_dir": "/tmp/demo"},
                headers=_AUTH,
            )
            resp = await client.post(
                "/api/record/step",
                json={"obs": {"image": "IMG"}, "action": {"actions": [0.2, 0.0]}},
                headers=_AUTH,
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["frames"] == 1

            # second step
            await client.post(
                "/api/record/step",
                json={"obs": {"image": "IMG2"}, "action": {"actions": [0.1, 0.0]}},
                headers=_AUTH,
            )

    _run(body())


def test_post_step_conflict_if_not_recording() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            resp = await client.post(
                "/api/record/step",
                json={"action": {"actions": [0.1, 0.0]}},
                headers=_AUTH,
            )
            assert resp.status == 409

    _run(body())


def test_delete_record_finalizes_and_calls_write_fn() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            await client.post(
                "/api/record",
                json={"prompt": "pick up", "out_dir": "/tmp/demo"},
                headers=_AUTH,
            )
            # write two steps
            for _ in range(3):
                await client.post(
                    "/api/record/step",
                    json={"obs": {}, "action": {"actions": [0.1, 0.0]}},
                    headers=_AUTH,
                )

            resp = await client.delete("/api/record", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["recording"] is False
            assert data["frames"] == 3
            assert "out_path" in data

            # write_fn was called with the right arguments
            assert len(_fake_write_fn.calls) == 1
            call = _fake_write_fn.calls[0]
            assert call["out_dir"] == "/tmp/demo"
            assert "pick-up" in call["repo_id"]
            episodes = call["episodes"]
            assert len(episodes) == 1
            assert len(episodes[0]) == 3

    _run(body())


def test_delete_record_conflict_if_not_active() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            resp = await client.delete("/api/record", headers=_AUTH)
            assert resp.status == 409

    _run(body())


def test_get_record_shows_frame_count() -> None:
    async def body() -> None:
        async with TestClient(TestServer(_app())) as client:
            await client.post(
                "/api/record",
                json={"prompt": "test", "out_dir": "/tmp/demo"},
                headers=_AUTH,
            )
            await client.post(
                "/api/record/step",
                json={"obs": {}, "action": {"actions": [0.1, 0.0]}},
                headers=_AUTH,
            )
            resp = await client.get("/api/record", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["recording"] is True
            assert data["frames"] == 1

    _run(body())
