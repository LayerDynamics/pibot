"""PolicyServerManager — manages the local openpi serve_policy.py subprocess (SPEC-3 FR-12).

Spawns the server in its own process group, probes its TCP port for health, and reports
:class:`PolicyServerState`. The `serve_cmd` factory is injectable for tests; the default
builds the real argv from the runbook command.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# (checkpoint, port) → argv list used to spawn the server
ServeCmd = Callable[[str, int], list[str]]


def _default_serve_cmd(checkpoint: str, port: int) -> list[str]:
    script = (
        Path(__file__).parent.parent.parent / "resources" / "openpi" / "scripts" / "serve_policy.py"
    )
    return [
        sys.executable,
        str(script),
        "--policy.config=pibot",
        f"--policy.dir={checkpoint}",
        f"--port={port}",
    ]


@dataclass
class PolicyServerState:
    host: str
    port: int
    pid: int | None
    checkpoint: str | None
    state: str  # "stopped" | "starting" | "running" | "error"
    last_infer_ms: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "pid": self.pid,
            "checkpoint": self.checkpoint,
            "state": self.state,
            "last_infer_ms": self.last_infer_ms,
        }


class PolicyServerManager:
    """Manages a single local policy-server subprocess."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8000,
        serve_cmd: ServeCmd | None = None,
        probe_timeout: float = 5.0,
    ) -> None:
        self._host = host
        self._port = port
        self._serve_cmd = serve_cmd or _default_serve_cmd
        self._probe_timeout = probe_timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._state = "stopped"
        self._checkpoint: str | None = None
        self._last_infer_ms: float | None = None

    async def start(self, checkpoint: str) -> PolicyServerState:
        """Start (or restart) the server for the given checkpoint path."""
        if self._proc is not None:
            await self.stop()
        cmd = self._serve_cmd(checkpoint, self._port)
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            start_new_session=True,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._checkpoint = checkpoint
        self._state = "starting"
        ok = await self._probe(self._probe_timeout)
        self._state = "running" if ok else "error"
        return self._as_state()

    async def stop(self) -> PolicyServerState:
        """Terminate the server; kill the process group on timeout."""
        if self._proc is None:
            self._state = "stopped"
            return self._as_state()
        try:
            self._proc.terminate()
            await asyncio.wait_for(self._proc.wait(), timeout=3.0)
        except (TimeoutError, ProcessLookupError):
            try:
                pgid = os.getpgid(self._proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            async with asyncio.timeout_at(asyncio.get_event_loop().time() + 2.0):
                try:
                    await self._proc.wait()
                except Exception:
                    pass
        self._proc = None
        self._state = "stopped"
        self._checkpoint = None
        self._last_infer_ms = None
        return self._as_state()

    def status(self) -> PolicyServerState:
        return self._as_state()

    def update_infer_ms(self, ms: float | None) -> None:
        """Called by the telemetry fan-out when a new policy.last_inference_ms arrives."""
        self._last_infer_ms = ms

    async def _probe(self, timeout: float) -> bool:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port), timeout=0.3
                )
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
                return True
            except (TimeoutError, OSError):
                await asyncio.sleep(0.05)
        return False

    def _as_state(self) -> PolicyServerState:
        return PolicyServerState(
            host=self._host,
            port=self._port,
            pid=self._proc.pid if self._proc else None,
            checkpoint=self._checkpoint,
            state=self._state,
            last_infer_ms=self._last_infer_ms,
        )
