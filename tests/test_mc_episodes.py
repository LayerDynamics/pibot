"""T12.4.5 — /api/episodes: read-only LeRobot episode browser."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp.test_utils import TestClient, TestServer

from pibot.mc.app import create_mc_app
from pibot.mc.datasets import EpisodeIndex
from pibot.ml.episode_logger import StepRecord

_AUTH = {"Authorization": "Bearer secret"}


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _rec(ep: int, fr: int, prompt: str = "drive") -> StepRecord:
    return StepRecord(
        obs={"image": {"base_0_rgb": "IMG"}, "state": [0.5, 0.0], "prompt": prompt},
        action={"actions": [0.2, 0.0]},
        ts=float(ep * 10 + fr),
        episode=ep,
        frame=fr,
        prompt=prompt,
    )


def _filled_index() -> EpisodeIndex:
    idx = EpisodeIndex()
    ep0 = [_rec(0, 0, "pick up"), _rec(0, 1, "pick up")]
    ep1 = [_rec(1, 0, "follow me")]
    idx.add_episodes([ep0], task="pick up")
    idx.add_episodes([ep1], task="follow me")
    return idx


# ---------------------------------------------------------------------------
# Unit: EpisodeIndex
# ---------------------------------------------------------------------------


def test_list_episodes_returns_metadata() -> None:
    idx = _filled_index()
    episodes = idx.list_episodes()
    assert len(episodes) == 2
    assert episodes[0]["id"] == "ep_000000"
    assert episodes[0]["task"] == "pick up"
    assert episodes[0]["length"] == 2
    assert episodes[1]["task"] == "follow me"
    assert episodes[1]["length"] == 1


def test_get_episode_returns_frames() -> None:
    idx = _filled_index()
    ep = idx.get_episode("ep_000000")
    assert ep is not None
    assert ep["length"] == 2
    frames = ep["frames"]
    assert len(frames) == 2
    assert frames[0]["episode_index"] == 0
    assert frames[0]["frame_index"] == 0
    assert frames[0]["observation.image"] == "IMG"
    assert frames[0]["task"] == "pick up"


def test_get_episode_missing_returns_none() -> None:
    idx = EpisodeIndex()
    assert idx.get_episode("ep_999999") is None


def test_index_never_mutates_dataset() -> None:
    idx = _filled_index()
    ep = idx.get_episode("ep_000000")
    assert ep is not None
    # Mutating the returned dict must not affect the internal state.
    ep["frames"].clear()
    assert idx.get_episode("ep_000000") is not None
    assert len(idx.get_episode("ep_000000")["frames"]) == 2  # type: ignore[index]


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------


def test_get_episodes_empty() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret", episode_index=EpisodeIndex())
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/episodes", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["episodes"] == []

    _run(body())


def test_get_episodes_lists_all() -> None:
    async def body() -> None:
        idx = _filled_index()
        app = create_mc_app(token="secret", episode_index=idx)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/episodes", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert len(data["episodes"]) == 2
            ids = {ep["id"] for ep in data["episodes"]}
            assert "ep_000000" in ids
            assert "ep_000001" in ids

    _run(body())


def test_get_episode_by_id() -> None:
    async def body() -> None:
        idx = _filled_index()
        app = create_mc_app(token="secret", episode_index=idx)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/episodes/ep_000000", headers=_AUTH)
            assert resp.status == 200
            data = await resp.json()
            assert data["id"] == "ep_000000"
            assert data["task"] == "pick up"
            assert len(data["frames"]) == 2

    _run(body())


def test_get_episode_not_found() -> None:
    async def body() -> None:
        app = create_mc_app(token="secret", episode_index=EpisodeIndex())
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/episodes/ep_999999", headers=_AUTH)
            assert resp.status == 404

    _run(body())


def test_get_episode_schema() -> None:
    async def body() -> None:
        idx = _filled_index()
        app = create_mc_app(token="secret", episode_index=idx)
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/episodes/ep_000001", headers=_AUTH)
            data = await resp.json()
            assert {"id", "task", "length", "started", "ended", "frames"} <= set(data)

    _run(body())
