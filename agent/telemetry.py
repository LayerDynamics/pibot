"""Telemetry collection: Pi health (vcgencmd + psutil) and robot sensors (MCU frames).

The text parsers are pure and fixture-tested; the live collectors are thin wrappers that
degrade gracefully off-Pi (no ``vcgencmd`` -> those fields are ``None``). The assembler
produces the snapshot schema from SPEC-1 §7 that the agent serves over ``/telemetry``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from pibot.protocol.codec import Message

# vcgencmd get_throttled bitmask: bits 0-3 are "currently", bits 16-19 are "since boot".
_THROTTLE_BITS = {
    0: "under_voltage",
    1: "freq_capped",
    2: "throttled",
    3: "soft_temp_limit",
}

_NUM_RE = re.compile(r"[-+]?\d*\.?\d+")

VcgencmdRun = Callable[[list[str]], str]


# ---- pure parsers --------------------------------------------------------


def _first_number(text: str) -> float:
    m = _NUM_RE.search(text)
    if m is None:
        raise ValueError(f"no number in {text!r}")
    return float(m.group())


def parse_temp(out: str) -> float:
    """Parse ``temp=42.8'C`` -> 42.8."""
    return _first_number(out.split("=", 1)[1])


def parse_volts(out: str) -> float:
    """Parse ``volt=0.8625V`` -> 0.8625."""
    return _first_number(out.split("=", 1)[1])


def decode_throttled(out: str) -> dict[str, Any]:
    """Decode ``throttled=0x...`` into raw value + human flag lists."""
    raw = int(out.split("=", 1)[1].strip(), 16)
    currently = [name for bit, name in _THROTTLE_BITS.items() if raw & (1 << bit)]
    since_boot = [name for bit, name in _THROTTLE_BITS.items() if raw & (1 << (bit + 16))]
    return {"raw": raw, "currently": currently, "since_boot": since_boot}


def parse_service_state(out: str) -> str:
    """Parse ``systemctl is-active`` output (``active`` / ``inactive`` / ...)."""
    return out.strip()


# ---- live collectors -----------------------------------------------------


def _default_vcgencmd(args: list[str]) -> str:
    import subprocess

    return subprocess.run(
        ["vcgencmd", *args], capture_output=True, text=True, timeout=5, check=True
    ).stdout


def read_vcgencmd(run: VcgencmdRun | None = None) -> dict[str, Any]:
    """Read SoC temp / throttle / core voltage. Fields are None if vcgencmd is absent."""
    run = run or _default_vcgencmd
    out: dict[str, Any] = {"temp_c": None, "throttled": None, "core_volt": None}
    try:
        out["temp_c"] = parse_temp(run(["measure_temp"]))
    except (OSError, ValueError, IndexError):
        pass
    try:
        out["throttled"] = decode_throttled(run(["get_throttled"]))
    except (OSError, ValueError, IndexError):
        pass
    try:
        out["core_volt"] = parse_volts(run(["measure_volts", "core"]))
    except (OSError, ValueError, IndexError):
        pass
    return out


def read_system_stats() -> dict[str, Any]:
    """CPU / memory / load / disk via psutil (works on Pi and dev machines)."""
    import psutil

    try:
        load = list(psutil.getloadavg())
    except (AttributeError, OSError):
        load = []
    disk = psutil.disk_usage("/")
    return {
        "cpu_pct": float(psutil.cpu_percent(interval=None)),
        "mem_pct": float(psutil.virtual_memory().percent),
        "load": load,
        "disk": {"mount": "/", "pct": float(disk.percent)},
    }


def pi_health(run: VcgencmdRun | None = None) -> dict[str, Any]:
    """Merge vcgencmd + psutil into one Pi-health dict."""
    return {**read_vcgencmd(run), **read_system_stats()}


# ---- robot telemetry accumulator -----------------------------------------


class RobotTelemetry:
    """Keeps the latest value per telemetry type as decoded MCU frames arrive."""

    def __init__(self) -> None:
        self._latest: dict[str, dict[str, Any]] = {}

    def ingest(self, msg: Message) -> None:
        self._latest[msg.name] = dict(msg.args)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: dict(args) for name, args in self._latest.items()}


def assemble_snapshot(
    *,
    pi: dict[str, Any],
    robot: dict[str, Any],
    transport: dict[str, Any],
    safety: dict[str, Any],
    ts: float,
) -> dict[str, Any]:
    """Build the SPEC-1 §7 telemetry snapshot."""
    return {"ts": ts, "pi": pi, "robot": robot, "transport": transport, "safety": safety}
