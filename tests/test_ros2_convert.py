"""Pure ROS 2 bridge conversions (no rclpy needed — runs in the normal gate)."""

from __future__ import annotations

from pibot.ros2.convert import snapshot_battery_volts, snapshot_estop, twist_to_drive


def test_twist_to_drive_passthrough() -> None:
    assert twist_to_drive(0.5, -0.2) == {"v": 0.5, "w": -0.2}


def test_twist_to_drive_applies_scales() -> None:
    assert twist_to_drive(1.0, 1.0, linear_scale=0.3, angular_scale=2.0) == {"v": 0.3, "w": 2.0}


def test_twist_to_drive_zero_is_stop() -> None:
    assert twist_to_drive(0.0, 0.0) == {"v": 0.0, "w": 0.0}


def test_snapshot_estop_reads_safety_block() -> None:
    assert snapshot_estop({"safety": {"estop": True}}) is True
    assert snapshot_estop({"safety": {"estop": False}}) is False
    assert snapshot_estop({}) is False  # missing block defaults to not-latched


def test_snapshot_battery_volts() -> None:
    assert snapshot_battery_volts({"robot": {"battery": {"volts": 12.4}}}) == 12.4
    assert snapshot_battery_volts({"robot": {"battery": {"volts": 11}}}) == 11.0
    assert snapshot_battery_volts({"robot": {}}) is None  # no battery reported
    assert snapshot_battery_volts({}) is None
    assert snapshot_battery_volts({"robot": {"battery": {"volts": None}}}) is None
    # a bool must not be mistaken for a voltage
    assert snapshot_battery_volts({"robot": {"battery": {"volts": True}}}) is None
