"""pibotd — the on-Pi agent.

A long-running asyncio service (aiohttp HTTP + WebSocket) that is the SOLE owner of the
transport to the robot, the central enforcer of safety (e-stop + deadman watchdog), and
the source of telemetry (Pi health + robot sensors). Mac-side clients (`pibot teleop`,
`pibot monitor`) are thin WebSocket clients of this agent.
"""

from __future__ import annotations

__version__ = "0.0.0"
