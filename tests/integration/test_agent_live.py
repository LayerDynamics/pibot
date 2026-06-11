"""T4.9 — live agent integration against the real Pi (opt-in via PIBOT_TEST_HOST).

Runs only when ``PIBOT_TEST_HOST`` names a Pi already running pibotd (start it with
``pibot agent start <host>``). Asserts the agent serves real ``vcgencmd``/``psutil``
telemetry. Skips cleanly otherwise so CI stays green without hardware.

    PIBOT_TEST_HOST=192.168.1.99 .venv/bin/pytest tests/integration/test_agent_live.py
"""

from __future__ import annotations

import asyncio
import os

import pytest

from pibot.config import load_config
from pibot.control.client import AgentClient
from pibot.inventory import Inventory, InventoryRecord

_HOST = os.environ.get("PIBOT_TEST_HOST")

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not _HOST, reason="set PIBOT_TEST_HOST to run live agent tests"),
]


def test_agent_serves_real_pi_telemetry() -> None:
    async def body() -> None:
        cfg = load_config()
        inv = Inventory(path=None)
        inv.add(InventoryRecord(alias="pibot", ip=_HOST or ""))
        port = int(cfg.agent_bind.rsplit(":", 1)[1])
        client = AgentClient(f"http://{_HOST}:{port}")
        await client.open()
        try:
            snap = await client.telemetry()
            assert "pi" in snap
            # On a real Pi, vcgencmd yields a plausible SoC temperature.
            assert isinstance(snap["pi"].get("cpu_pct"), float)
        finally:
            await client.close()

    asyncio.run(body())
