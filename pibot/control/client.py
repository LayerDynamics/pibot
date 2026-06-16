"""AgentClient — a WebSocket/HTTP client of the pibotd agent (used by teleop/monitor).

Thin async wrapper over the agent's control surface: a persistent ``WS /control`` for
commands, plus one-shot ``POST /estop``, ``GET /telemetry``, and a ``WS /telemetry``
stream. Authenticates with the bearer token when reaching the agent over the network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import aiohttp


class AgentClient:
    def __init__(self, base_url: str, token: str | None = None) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._arm_ws: aiohttp.ClientWebSocketResponse | None = None

    async def open(self) -> None:
        """Open the HTTP session only (telemetry/estop) — no control socket."""
        if self._session is None:
            self._session = aiohttp.ClientSession(headers=self._headers)

    async def connect(self) -> None:
        """Open the session and the persistent control WebSocket."""
        await self.open()
        assert self._session is not None
        self._ws = await self._session.ws_connect(self._base + "/control")

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def send_command(self, cmd: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a command over the control socket and return the agent's reply."""
        if self._ws is None:
            raise RuntimeError("client not connected")
        await self._ws.send_json({"cmd": cmd, "args": args or {}})
        reply: dict[str, Any] = await self._ws.receive_json()
        return reply

    async def estop(self) -> dict[str, Any]:
        assert self._session is not None
        async with self._session.post(self._base + "/estop") as resp:
            data: dict[str, Any] = await resp.json()
            return data

    async def telemetry(self) -> dict[str, Any]:
        assert self._session is not None
        async with self._session.get(self._base + "/telemetry") as resp:
            data: dict[str, Any] = await resp.json()
            return data

    async def arm_telemetry(self) -> dict[str, Any]:
        """Read-only stepper-arm joint angles (``GET /arm/telemetry``). ``enabled`` is False
        when the agent has no arm configured."""
        assert self._session is not None
        async with self._session.get(self._base + "/arm/telemetry") as resp:
            data: dict[str, Any] = await resp.json()
            return data

    # ---- arm motion (WS /arm/control) ---------------------------------------------------
    # Each call sends one frame over a lazily-opened, persistent ``/arm/control`` socket and
    # returns the agent's per-frame reply (``{"type": "ack"}`` or ``{"type": "nak", "reason"}``).
    # The host safety gate lives in pibotd; this is a thin transport for its frames.

    async def _arm_send(self, frame: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("client not open")
        if self._arm_ws is None or self._arm_ws.closed:
            self._arm_ws = await self._session.ws_connect(self._base + "/arm/control")
        await self._arm_ws.send_json(frame)
        reply: dict[str, Any] = await self._arm_ws.receive_json()
        return reply

    async def arm_jog(self, joint: int, dps: float) -> dict[str, Any]:
        """Velocity-jog a joint (deg/sec); 0 stops it. No homing required."""
        return await self._arm_send({"cmd": "jvel", "joint": joint, "dps": dps})

    async def arm_move_joint(
        self, joint: int, deg: float, speed: float | None = None
    ) -> dict[str, Any]:
        """Move a joint to an absolute angle — at its configured speed (``jpos``) or, when
        ``speed`` is given, at that speed (``jmove``). Requires the joint to be homed."""
        frame: dict[str, Any] = {"cmd": "jpos", "joint": joint, "deg": deg}
        if speed is not None:
            frame = {"cmd": "jmove", "joint": joint, "deg": deg, "dps": speed}
        return await self._arm_send(frame)

    async def arm_move_joints(self, targets: dict[int, float], seconds: float) -> dict[str, Any]:
        """Move several joints to arrive together after ``seconds`` (synchronized)."""
        return await self._arm_send({"cmd": "move", "targets": targets, "seconds": seconds})

    async def arm_home(self, joint: int) -> dict[str, Any]:
        """Home one joint against its endstop."""
        return await self._arm_send({"cmd": "home", "joint": joint})

    async def arm_estop(self) -> dict[str, Any]:
        """Latch the arm e-stop (all motion refused until cleared)."""
        return await self._arm_send({"cmd": "estop"})

    async def arm_clear_estop(self) -> dict[str, Any]:
        """Clear the arm e-stop latch."""
        return await self._arm_send({"cmd": "clear_estop"})

    async def arm_enable(self, on: bool) -> dict[str, Any]:
        """Energize (``True``) or release (``False``) the arm steppers."""
        return await self._arm_send({"cmd": "enable", "on": on})

    async def arm_grip(self, deg: float) -> dict[str, Any]:
        """Drive the servo gripper to an absolute angle (deg); the board angle-clamps it."""
        return await self._arm_send({"cmd": "grip", "deg": deg})

    async def arm_tool(self, on: bool) -> dict[str, Any]:
        """Energize (``True``) or release (``False``) the digital-output tool."""
        return await self._arm_send({"cmd": "tool", "on": on})

    async def autonomy_start(
        self, *, prompt: str, max_speed: float | None = None, control_hz: float | None = None
    ) -> dict[str, Any]:
        """Ask the agent to start in-process closed-loop autonomy (through its safety gate)."""
        assert self._session is not None
        payload: dict[str, Any] = {"prompt": prompt}
        if max_speed is not None:
            payload["max_speed"] = max_speed
        if control_hz is not None:
            payload["control_hz"] = control_hz
        async with self._session.post(self._base + "/autonomy", json=payload) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"Failed to start autonomy ({resp.status}): {text}")
            data: dict[str, Any] = await resp.json()
            return data

    async def autonomy_stop(self) -> dict[str, Any]:
        assert self._session is not None
        async with self._session.delete(self._base + "/autonomy") as resp:
            data: dict[str, Any] = await resp.json()
            return data

    async def telemetry_stream(self) -> AsyncIterator[dict[str, Any]]:
        assert self._session is not None
        ws = await self._session.ws_connect(self._base + "/telemetry")
        try:
            async for msg in ws:
                if msg.type is aiohttp.WSMsgType.TEXT:
                    yield msg.json()
                else:
                    break
        finally:
            await ws.close()

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        if self._arm_ws is not None:
            await self._arm_ws.close()
            self._arm_ws = None
        if self._session is not None:
            await self._session.close()
            self._session = None
