"""``pibot monitor`` — live robot + Pi health dashboard with threshold alerts.

Polls the agent's ``/telemetry`` snapshot (SPEC-1 §7), renders it (TUI / ``--json`` /
``--csv``), and raises a non-zero exit code on any threshold breach (hot SoC, throttling,
low battery, transport down, e-stop latched) or if the agent is unreachable — so it
composes in scripts and CI.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pibot.config import Config
from pibot.control.client import AgentClient
from pibot.inventory import Inventory


def check_thresholds(
    snap: dict[str, Any],
    *,
    temp_warn: float = 80.0,
    battery_warn: float = 11.0,
    policy_stale_ms: float = 1000.0,
) -> list[str]:
    """Return human-readable alert strings for any breached threshold (empty = OK)."""
    alerts: list[str] = []
    pi = snap.get("pi", {})
    temp = pi.get("temp_c")
    if temp is not None and temp >= temp_warn:
        alerts.append(f"temp {temp}°C ≥ {temp_warn}°C")
    throttled = pi.get("throttled") or {}
    if throttled.get("currently"):
        alerts.append("throttled: " + ", ".join(throttled["currently"]))
    battery = snap.get("robot", {}).get("battery", {}).get("volts")
    if battery is not None and battery < battery_warn:
        alerts.append(f"battery {battery}V < {battery_warn}V")
    transport = snap.get("transport") or {}
    if transport.get("open") is False:
        alerts.append("transport down")
    if snap.get("safety", {}).get("estop"):
        alerts.append("e-stop latched")
    # policy-link (only when an autonomy session is attached: connected is None -> no session)
    policy = snap.get("policy") or {}
    if policy.get("connected") is False:
        alerts.append("policy down")
    chunk_age = policy.get("chunk_age_ms")
    if chunk_age is not None and chunk_age >= policy_stale_ms:
        alerts.append(f"policy chunk stale {chunk_age}ms ≥ {policy_stale_ms}ms")
    return alerts


def render_snapshot(snap: dict[str, Any], alerts: list[str]) -> list[str]:
    """Render a snapshot to human-readable TUI lines."""
    pi = snap.get("pi", {})
    robot = snap.get("robot", {})
    tr = snap.get("transport", {})
    disk = pi.get("disk", {})
    battery_v = robot.get("battery", {}).get("volts")
    estop = snap.get("safety", {}).get("estop")
    policy = snap.get("policy", {})
    lines = [
        f"temp {pi.get('temp_c')}°C  core {pi.get('core_volt')}V  "
        f"cpu {pi.get('cpu_pct')}%  mem {pi.get('mem_pct')}%  disk {disk.get('pct')}%",
        f"transport {tr.get('backend')} open={tr.get('open')}  battery {battery_v}V  estop={estop}",
        f"policy connected={policy.get('connected')}  "
        f"infer {policy.get('last_inference_ms')}ms  chunk_age {policy.get('chunk_age_ms')}ms",
    ]
    for alert in alerts:
        lines.append(f"  ALERT: {alert}")
    return lines


_CSV_FIELDS = [
    "ts",
    "temp_c",
    "core_volt",
    "cpu_pct",
    "mem_pct",
    "disk_pct",
    "battery_v",
    "transport_open",
    "estop",
    "policy_connected",
    "policy_infer_ms",
    "policy_chunk_age_ms",
]


def snapshot_csv_header() -> str:
    return ",".join(_CSV_FIELDS)


def snapshot_to_csv(snap: dict[str, Any]) -> str:
    pi = snap.get("pi", {})
    policy = snap.get("policy", {})
    row = [
        snap.get("ts"),
        pi.get("temp_c"),
        pi.get("core_volt"),
        pi.get("cpu_pct"),
        pi.get("mem_pct"),
        pi.get("disk", {}).get("pct"),
        snap.get("robot", {}).get("battery", {}).get("volts"),
        snap.get("transport", {}).get("open"),
        snap.get("safety", {}).get("estop"),
        policy.get("connected"),
        policy.get("last_inference_ms"),
        policy.get("chunk_age_ms"),
    ]
    return ",".join("" if v is None else str(v) for v in row)


def _agent_port(cfg: Config) -> int:
    return int(cfg.agent_bind.rsplit(":", 1)[1])


async def monitor(
    target: str,
    *,
    cfg: Config,
    inventory: Inventory,
    once: bool = True,
    as_json: bool = False,
    as_csv: bool = False,
    interval: float = 1.0,
    max_polls: int | None = None,
    client: AgentClient | Any | None = None,
) -> int:
    """Poll the agent's telemetry and render it; return 1 on alerts, 2 if unreachable."""
    own = client is None
    if own:
        address = inventory.resolve(target)
        from agent.auth import load_token

        client = AgentClient(
            f"http://{address}:{_agent_port(cfg)}", token=load_token(cfg.agent_token_path)
        )
        await client.open()
    assert client is not None  # set above when own, else supplied by caller

    worst = 0
    polls = 0
    try:
        while True:
            try:
                snap = await client.telemetry()
            except Exception as exc:  # agent unreachable / connection error
                print(f"agent unreachable: {exc}")
                return 2
            alerts = check_thresholds(snap, temp_warn=cfg.temp_warn_c)
            if as_json:
                print(json.dumps(snap))
            elif as_csv:
                if polls == 0:
                    print(snapshot_csv_header())
                print(snapshot_to_csv(snap))
            else:
                for line in render_snapshot(snap, alerts):
                    print(line)
            if alerts:
                worst = 1
            polls += 1
            if once or (max_polls is not None and polls >= max_polls):
                break
            await asyncio.sleep(interval)
    finally:
        if own:
            await client.close()
    return worst
