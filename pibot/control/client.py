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
        if self._session is not None:
            await self._session.close()
            self._session = None
