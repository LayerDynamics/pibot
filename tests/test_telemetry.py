"""T4.4 — telemetry parsers (vcgencmd, throttle bitmask, psutil) + snapshot assembly."""

from __future__ import annotations

from agent import telemetry
from agent.telemetry import (
    RobotTelemetry,
    assemble_snapshot,
    decode_throttled,
    parse_service_state,
    parse_temp,
    parse_volts,
    read_vcgencmd,
)
from pibot.protocol.codec import Message, MessageType


def test_parse_temp() -> None:
    assert parse_temp("temp=42.8'C\n") == 42.8
    assert parse_temp("temp=0.0'C") == 0.0


def test_parse_volts() -> None:
    assert parse_volts("volt=0.8625V\n") == 0.8625


def test_decode_throttled_clear() -> None:
    d = decode_throttled("throttled=0x0\n")
    assert d["raw"] == 0
    assert d["currently"] == []
    assert d["since_boot"] == []


def test_decode_throttled_since_boot() -> None:
    # 0x50000 -> bit 16 (under-voltage since boot) + bit 18 (throttled since boot)
    d = decode_throttled("throttled=0x50000")
    assert d["since_boot"] == ["under_voltage", "throttled"]
    assert d["currently"] == []


def test_decode_throttled_currently() -> None:
    # 0x5 -> bit 0 (under-voltage now) + bit 2 (throttled now)
    d = decode_throttled("throttled=0x5")
    assert d["currently"] == ["under_voltage", "throttled"]


def test_decode_throttled_all_bits() -> None:
    d = decode_throttled("throttled=0xF000F")  # bits 0-3 now + 16-19 since boot
    assert d["currently"] == ["under_voltage", "freq_capped", "throttled", "soft_temp_limit"]
    assert d["since_boot"] == ["under_voltage", "freq_capped", "throttled", "soft_temp_limit"]


def test_parse_service_state() -> None:
    assert parse_service_state("active\n") == "active"
    assert parse_service_state("inactive") == "inactive"


def test_read_vcgencmd_with_injected_runner() -> None:
    outputs = {
        ("measure_temp",): "temp=55.3'C\n",
        ("get_throttled",): "throttled=0x0\n",
        ("measure_volts", "core"): "volt=0.9000V\n",
    }
    health = read_vcgencmd(run=lambda args: outputs[tuple(args)])
    assert health["temp_c"] == 55.3
    assert health["core_volt"] == 0.9
    assert health["throttled"]["raw"] == 0


def test_read_vcgencmd_absent_tool_yields_none() -> None:
    def missing(args: list[str]) -> str:
        raise FileNotFoundError("vcgencmd")

    health = read_vcgencmd(run=missing)
    assert health["temp_c"] is None
    assert health["throttled"] is None


def test_system_stats_has_expected_keys_live() -> None:
    stats = telemetry.read_system_stats()  # real psutil on this machine
    assert "cpu_pct" in stats
    assert "mem_pct" in stats
    assert isinstance(stats["cpu_pct"], float)
    assert "disk" in stats


def test_robot_telemetry_accumulates_latest() -> None:
    rt = RobotTelemetry()
    rt.ingest(Message(MessageType.TELEMETRY, 1, "battery", {"volts": 12.4}))
    rt.ingest(Message(MessageType.TELEMETRY, 2, "current", {"amps": 1.5}))
    rt.ingest(Message(MessageType.TELEMETRY, 3, "battery", {"volts": 12.1}))  # newer wins
    snap = rt.snapshot()
    assert snap["battery"] == {"volts": 12.1}
    assert snap["current"] == {"amps": 1.5}


def test_assemble_snapshot_schema() -> None:
    snap = assemble_snapshot(
        pi={"temp_c": 50.0},
        robot={"battery": {"volts": 12.4}},
        transport={"backend": "tcp", "open": True},
        safety={"estop": False, "watchdog_ok": True},
        ts=1234.5,
    )
    assert snap["ts"] == 1234.5
    assert snap["pi"]["temp_c"] == 50.0
    assert snap["robot"]["battery"]["volts"] == 12.4
    assert snap["transport"]["backend"] == "tcp"
    assert snap["safety"]["estop"] is False
