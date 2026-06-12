"""Shared control-plane state, split out so route modules can import ``STATE`` without an
import cycle through ``app``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from aiohttp import web

from pibot.mc import __version__
from pibot.mc.robot_link import RobotLink

# Invoked on a successful connect with (robot base_url, token) — the Rust endpoint-cache seam.
OnRobotConnect = Callable[[str, "str | None"], None]


@dataclass
class McState:
    """Shared, typed control-plane state."""

    token: str | None = None
    version: str = __version__
    started: float = field(default_factory=time.monotonic)
    connected: bool = False
    robot: str | None = None
    link: RobotLink | None = None
    on_robot_connect: OnRobotConnect | None = None


STATE: web.AppKey[McState] = web.AppKey("pibot_mc_state", McState)
