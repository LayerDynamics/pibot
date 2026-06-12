"""T4.7 — pibot monitor: threshold alerts (exit codes), rendering, CSV, --once/stream."""

from __future__ import annotations

import asyncio
import json

from pibot import monitor
from pibot.config import Config
from pibot.inventory import Inventory, InventoryRecord


def _inv() -> Inventory:
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip="192.168.1.99"))
    return inv


def _snap(
    temp=50.0, throttled_now=None, battery=12.4, open_=True, estop=False, policy=None
) -> dict:
    return {
        "ts": 1.0,
        "pi": {
            "temp_c": temp,
            "throttled": {"raw": 0, "currently": throttled_now or [], "since_boot": []},
            "core_volt": 0.88,
            "cpu_pct": 10.0,
            "mem_pct": 30.0,
            "disk": {"mount": "/", "pct": 50.0},
        },
        "robot": {"battery": {"volts": battery}},
        "transport": {"backend": "tcp", "open": open_},
        "safety": {"estop": estop},
        "policy": policy or {"connected": None, "last_inference_ms": None, "chunk_age_ms": None},
    }


class _FakeClient:
    def __init__(self, snap: dict, *, raise_exc: Exception | None = None) -> None:
        self._snap = snap
        self._raise = raise_exc

    async def telemetry(self) -> dict:
        if self._raise is not None:
            raise self._raise
        return self._snap

    async def close(self) -> None:
        pass


def _run(coro):
    return asyncio.run(coro)


# ---- thresholds ----------------------------------------------------------


def test_check_thresholds_ok() -> None:
    assert monitor.check_thresholds(_snap(), temp_warn=80.0) == []


def test_check_thresholds_breaches() -> None:
    assert any("temp" in a for a in monitor.check_thresholds(_snap(temp=85.0), temp_warn=80.0))
    assert any(
        "throttled" in a for a in monitor.check_thresholds(_snap(throttled_now=["under_voltage"]))
    )
    assert any("battery" in a for a in monitor.check_thresholds(_snap(battery=10.0)))
    assert any("transport" in a for a in monitor.check_thresholds(_snap(open_=False)))
    assert any("e-stop" in a for a in monitor.check_thresholds(_snap(estop=True)))


def test_no_policy_session_does_not_alert() -> None:
    # connected is None (no autonomy running) -> not an alert, like transport open=None.
    assert monitor.check_thresholds(_snap()) == []


def test_check_thresholds_policy_down_and_stale_chunk() -> None:
    down = _snap(policy={"connected": False, "last_inference_ms": 40.0, "chunk_age_ms": 10.0})
    assert any("policy" in a and "down" in a for a in monitor.check_thresholds(down))

    stale = _snap(policy={"connected": True, "last_inference_ms": 40.0, "chunk_age_ms": 5000.0})
    assert any("stale" in a for a in monitor.check_thresholds(stale, policy_stale_ms=1000.0))

    fresh = _snap(policy={"connected": True, "last_inference_ms": 40.0, "chunk_age_ms": 20.0})
    assert monitor.check_thresholds(fresh, policy_stale_ms=1000.0) == []


def test_render_snapshot_includes_key_values() -> None:
    snap = _snap(
        temp=63.0, policy={"connected": True, "last_inference_ms": 42.0, "chunk_age_ms": 5.0}
    )
    lines = "\n".join(monitor.render_snapshot(snap, []))
    assert "63" in lines
    assert "tcp" in lines
    assert "policy" in lines and "42" in lines  # policy line rendered


def test_csv_row_and_header() -> None:
    header = monitor.snapshot_csv_header()
    snap = _snap(
        temp=63.0, policy={"connected": True, "last_inference_ms": 42.0, "chunk_age_ms": 5.0}
    )
    row = monitor.snapshot_to_csv(snap)
    assert "temp_c" in header
    assert "policy_connected" in header and "policy_infer_ms" in header
    assert "63.0" in row
    assert "42.0" in row  # last_inference_ms in the row


# ---- monitor loop --------------------------------------------------------


def test_monitor_once_json_returns_zero(capsys) -> None:
    rc = _run(
        monitor.monitor(
            "pibot",
            cfg=Config(),
            inventory=_inv(),
            once=True,
            as_json=True,
            client=_FakeClient(_snap()),
        )
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["pi"]["temp_c"] == 50.0


def test_monitor_alert_returns_nonzero() -> None:
    rc = _run(
        monitor.monitor(
            "pibot",
            cfg=Config(temp_warn_c=80.0),
            inventory=_inv(),
            once=True,
            client=_FakeClient(_snap(temp=90.0)),
        )
    )
    assert rc == 1


def test_monitor_unreachable_returns_two() -> None:
    rc = _run(
        monitor.monitor(
            "pibot",
            cfg=Config(),
            inventory=_inv(),
            once=True,
            client=_FakeClient(_snap(), raise_exc=OSError("refused")),
        )
    )
    assert rc == 2
