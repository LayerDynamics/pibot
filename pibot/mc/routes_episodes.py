"""T12.4.5 — /api/episodes: read-only LeRobot episode browser."""

from __future__ import annotations

from aiohttp import web

from pibot.mc.datasets import EpisodeIndex

EPISODE_INDEX: web.AppKey[EpisodeIndex] = web.AppKey("pibot_mc_episodes", EpisodeIndex)


async def handle_list_episodes(request: web.Request) -> web.Response:
    """GET /api/episodes — list all episodes."""
    index = request.app[EPISODE_INDEX]
    return web.json_response({"episodes": index.list_episodes()})


async def handle_get_episode(request: web.Request) -> web.Response:
    """GET /api/episodes/{id} — per-episode metadata + frames."""
    index = request.app[EPISODE_INDEX]
    ep_id = request.match_info["id"]
    ep = index.get_episode(ep_id)
    if ep is None:
        raise web.HTTPNotFound(text=f"episode {ep_id} not found")
    return web.json_response(ep)


def add_episodes_routes(
    app: web.Application,
    *,
    episode_index: EpisodeIndex | None = None,
) -> None:
    index = episode_index or EpisodeIndex()
    app[EPISODE_INDEX] = index
    app.router.add_get("/api/episodes", handle_list_episodes)
    app.router.add_get("/api/episodes/{id}", handle_get_episode)
