"""T12.4.4 — /api/record: start/stop demonstration recording via SPEC-2 EpisodeLogger.

POST /api/record      — start a new recording episode (prompt, out_dir)
POST /api/record/step — append one step (obs, action) to the active episode
GET  /api/record      — recording status
DELETE /api/record    — finalize the episode and write the dataset

The ``write_fn`` is injectable so CI can test without the lerobot dependency.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from aiohttp import web

from pibot.ml.episode_logger import EpisodeLogger

WriteFn = Callable[[list[list[Any]], str, str], str]

DEMO_RECORDER: web.AppKey[DemoRecorderState] = web.AppKey(
    "pibot_mc_demo_recorder",
    object,  # type: ignore[arg-type]
)


def _default_write_fn(episodes: list[list[Any]], out_dir: str, repo_id: str) -> str:
    from pibot.ml.dataset import write_dataset  # lerobot dep — only on M4 Max

    return write_dataset(episodes, out_dir, repo_id=repo_id)


@dataclasses.dataclass
class DemoRecorderState:
    logger: EpisodeLogger = dataclasses.field(default_factory=EpisodeLogger)
    active: bool = False
    prompt: str = ""
    out_dir: str = ""
    write_fn: WriteFn = dataclasses.field(default=_default_write_fn)


async def handle_post_record(request: web.Request) -> web.Response:
    """POST /api/record — start a new recording session."""
    rec = request.app[DEMO_RECORDER]
    if rec.active:
        raise web.HTTPConflict(text="recording already in progress")
    body = await request.json()
    prompt = body.get("prompt", "")
    out_dir = body.get("out_dir", "")
    if not out_dir:
        raise web.HTTPBadRequest(text="out_dir required")
    rec.logger = EpisodeLogger()
    rec.prompt = str(prompt)
    rec.out_dir = str(out_dir)
    rec.active = True
    rec.logger.start_episode(rec.prompt)
    return web.json_response({"recording": True, "prompt": rec.prompt}, status=201)


async def handle_post_step(request: web.Request) -> web.Response:
    """POST /api/record/step — append one observation+action step."""
    rec = request.app[DEMO_RECORDER]
    if not rec.active:
        raise web.HTTPConflict(text="no active recording")
    body = await request.json()
    obs = body.get("obs")
    action = body.get("action")
    if action is None:
        raise web.HTTPBadRequest(text="action required")
    rec.logger.on_step(obs, action)
    return web.json_response({"frames": len(rec.logger.records)})


async def handle_get_record(request: web.Request) -> web.Response:
    """GET /api/record — current recording status."""
    rec = request.app[DEMO_RECORDER]
    return web.json_response(
        {
            "recording": rec.active,
            "prompt": rec.prompt if rec.active else None,
            "frames": len(rec.logger.records) if rec.active else 0,
        }
    )


async def handle_delete_record(request: web.Request) -> web.Response:
    """DELETE /api/record — finalize + write the episode dataset."""
    rec = request.app[DEMO_RECORDER]
    if not rec.active:
        raise web.HTTPConflict(text="no active recording")
    rec.active = False
    rec.logger.end_episode()
    episodes = rec.logger.episodes()
    frames = sum(len(ep) for ep in episodes)
    repo_id = f"pibot-{rec.prompt}".replace(" ", "-") or "pibot-demo"
    out_path = rec.write_fn(episodes, rec.out_dir, repo_id)
    return web.json_response(
        {
            "recording": False,
            "frames": frames,
            "out_path": out_path,
            "repo_id": repo_id,
        }
    )


def add_record_routes(
    app: web.Application,
    *,
    write_fn: WriteFn | None = None,
) -> None:
    state = DemoRecorderState()
    if write_fn is not None:
        state.write_fn = write_fn
    app[DEMO_RECORDER] = state
    app.router.add_post("/api/record", handle_post_record)
    app.router.add_post("/api/record/step", handle_post_step)
    app.router.add_get("/api/record", handle_get_record)
    app.router.add_delete("/api/record", handle_delete_record)
