"""Pure conversions between ROS 2 message fields and pibot agent JSON — no rclpy import.

Split from :mod:`pibot.ros2.bridge` so the mapping logic runs in the normal pytest gate
(which has no ROS 2), while the bridge stays a thin rclpy wrapper exercised only on the robot.
"""

from __future__ import annotations

from typing import Any


def twist_to_drive(
    linear_x: float,
    angular_z: float,
    *,
    linear_scale: float = 1.0,
    angular_scale: float = 1.0,
) -> dict[str, float]:
    """Map a ``geometry_msgs/Twist`` (``linear.x``, ``angular.z``) to a pibot ``drive`` command.

    ``linear_scale`` / ``angular_scale`` are tunable ROS params (m·s⁻¹ / rad·s⁻¹ → pibot
    drive units). The agent's safety gate still clamps the result to the robot's configured
    limits, so out-of-range twists are bounded downstream — never silently here.
    """
    return {
        "v": float(linear_x) * float(linear_scale),
        "w": float(angular_z) * float(angular_scale),
    }


def snapshot_estop(snap: dict[str, Any]) -> bool:
    """Extract the latched e-stop state from a pibot telemetry snapshot (default False)."""
    safety = snap.get("safety") or {}
    return bool(safety.get("estop", False))


def snapshot_battery_volts(snap: dict[str, Any]) -> float | None:
    """Extract battery volts from a snapshot, or ``None`` when the robot reports none."""
    robot = snap.get("robot") or {}
    battery = robot.get("battery") or {}
    volts = battery.get("volts")
    return float(volts) if isinstance(volts, (int, float)) and not isinstance(volts, bool) else None
