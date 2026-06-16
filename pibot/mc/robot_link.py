"""Robot-link manager (SPEC-3 §3.2): owns the single active ``AgentClient`` to a robot's
``pibotd`` over Nebula, and relays its telemetry to the webview.

On connect it invokes ``on_connect(url, token)`` — the seam the Rust core uses to cache the
robot endpoint for the e-stop failsafe (wired in M12.2 T12.2.7). The manager never
re-implements the link: it delegates to the existing ``pibot.control.client.AgentClient``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import aiohttp

from agent.auth import load_token
from pibot.config import load_config
from pibot.control.client import AgentClient
from pibot.inventory import Inventory
from pibot.mc.video_relay import VideoRelay

# (robot alias) -> (base_url, bearer token)
Resolver = Callable[[str], "tuple[str, str | None]"]
ClientFactory = Callable[[str, "str | None"], AgentClient]
OnConnect = Callable[[str, "str | None"], None]


def resolve_robot_endpoint(robot: str) -> tuple[str, str | None]:
    """Resolve a robot alias to its ``pibotd`` base URL + bearer token from disk state."""
    cfg = load_config()
    inv = Inventory.load()
    address = inv.resolve(robot)
    port = int(cfg.agent_bind.rsplit(":", 1)[1])
    return f"http://{address}:{port}", load_token(cfg.agent_token_path)


class RobotLink:
    def __init__(
        self,
        *,
        resolver: Resolver = resolve_robot_endpoint,
        client_factory: ClientFactory = AgentClient,
        on_connect: OnConnect | None = None,
    ) -> None:
        self._resolver = resolver
        self._client_factory = client_factory
        self._on_connect = on_connect
        self._client: AgentClient | None = None
        self._robot: str | None = None
        self._robot_url: str | None = None
        self._robot_token: str | None = None
        self._video_relay: VideoRelay | None = None
        self._video_session: aiohttp.ClientSession | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None

    @property
    def robot(self) -> str | None:
        return self._robot

    @property
    def robot_url(self) -> str | None:
        return self._robot_url

    @property
    def robot_token(self) -> str | None:
        return self._robot_token

    @property
    def video_relay(self) -> VideoRelay | None:
        """The active :class:`~pibot.mc.video_relay.VideoRelay`, or ``None`` if not connected."""
        return self._video_relay

    async def connect(self, robot: str) -> dict[str, Any]:
        """Open the link to ``robot``; replaces any existing connection."""
        if self._client is not None:
            await self.disconnect()
        url, token = self._resolver(robot)
        client = self._client_factory(url, token)
        await client.open()
        self._client = client
        self._robot = robot
        self._robot_url = url
        self._robot_token = token
        if self._on_connect is not None:
            # Hand the robot endpoint to the Rust core for the e-stop failsafe (M12.2).
            self._on_connect(url, token)

        # Open a dedicated session for the video relay (separate from control/telemetry).
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._video_session = aiohttp.ClientSession(headers=headers)
        ws_url = url.replace("http://", "ws://").replace("https://", "wss://") + "/video"
        self._video_relay = VideoRelay(self._video_session, ws_url)
        self._video_relay.start()

        return {"robot": robot, "url": url}

    async def disconnect(self) -> None:
        if self._video_relay is not None:
            await self._video_relay.stop()
            self._video_relay = None
        if self._video_session is not None:
            await self._video_session.close()
            self._video_session = None
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._robot = None
            self._robot_url = None
            self._robot_token = None

    def telemetry_stream(self) -> AsyncIterator[dict[str, Any]]:
        if self._client is None:
            raise RuntimeError("not connected")
        return self._client.telemetry_stream()

    async def arm_telemetry(self) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.arm_telemetry()

    # ---- arm motion — delegated to AgentClient (never a second link) ---------------------

    async def arm_jog(self, joint: int, dps: float) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.arm_jog(joint, dps)

    async def arm_move_joint(
        self, joint: int, deg: float, speed: float | None = None
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.arm_move_joint(joint, deg, speed)

    async def arm_move_joints(self, targets: dict[int, float], seconds: float) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.arm_move_joints(targets, seconds)

    async def arm_home(self, joint: int) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.arm_home(joint)

    async def arm_estop(self) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.arm_estop()

    async def arm_clear_estop(self) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.arm_clear_estop()

    async def arm_enable(self, on: bool) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.arm_enable(on)

    async def arm_grip(self, deg: float) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.arm_grip(deg)

    async def arm_tool(self, on: bool) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.arm_tool(on)

    async def autonomy_start(
        self,
        *,
        prompt: str,
        max_speed: float | None = None,
        control_hz: float | None = None,
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.autonomy_start(
            prompt=prompt, max_speed=max_speed, control_hz=control_hz
        )

    async def autonomy_stop(self) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        return await self._client.autonomy_stop()

    async def autonomy_status(self) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("not connected")
        snap = await self._client.telemetry()
        policy = snap.get("policy")
        return {"running": bool(policy and policy.get("connected")), "policy": policy}
