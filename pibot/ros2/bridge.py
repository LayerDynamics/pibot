"""rclpy bridge: exposes the pibotd agent on the ROS 2 graph (run on the robot).

``python -m pibot.ros2.bridge`` (with ROS 2 sourced). It connects to the local pibotd agent
through :class:`~pibot.control.client.AgentClient` — loopback is trusted, so no token is
needed — and never re-implements the link. It bridges:

  ROS 2 → pibot   ``/cmd_vel`` (geometry_msgs/Twist) → ``drive`` commands through the agent's
                  safety gate, re-sent at a fixed rate with a command-timeout deadman (no
                  recent Twist → stop), so a dead teleop publisher halts the robot.
  pibot → ROS 2   ``/pibot/telemetry`` (std_msgs/String JSON), ``/pibot/estop``
                  (std_msgs/Bool), ``/pibot/battery`` (sensor_msgs/BatteryState), and
                  ``/pibot/image/compressed`` (sensor_msgs/CompressedImage from WS /video).

ROS params (``--ros-args -p name:=value``): ``agent_url`` (default
``http://127.0.0.1:8787``), ``agent_token`` (default empty = loopback-trusted),
``drive_rate_hz`` (20), ``cmd_timeout_s`` (0.5), ``linear_scale`` / ``angular_scale`` (1.0),
``video_enabled`` (true).

rclpy / message packages / aiohttp are imported lazily so importing :mod:`pibot.ros2` never
pulls ROS 2 onto the core suite's import path. The whole node runs single-threaded on one
asyncio loop (``rclpy.spin_once`` is pumped as a task), so the ``/cmd_vel`` callback and the
publishers need no locking.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any

from pibot.ros2.convert import snapshot_battery_volts, snapshot_estop, twist_to_drive


class Bridge:
    """Owns the async loops that move data between pibotd and the ROS 2 node."""

    def __init__(
        self,
        node: Any,
        pubs: dict[str, Any],
        *,
        agent_url: str,
        token: str | None,
        drive_rate: float,
        cmd_timeout: float,
        lin_scale: float,
        ang_scale: float,
        video_enabled: bool,
    ) -> None:
        self._node = node
        self._pubs = pubs
        self._agent_url = agent_url
        self._token = token
        self._drive_rate = drive_rate
        self._cmd_timeout = cmd_timeout
        self._lin_scale = lin_scale
        self._ang_scale = ang_scale
        self._video_enabled = video_enabled
        self._latest: tuple[float, float] = (0.0, 0.0)
        self._last_cmd = 0.0

    def on_cmd_vel(self, msg: Any) -> None:
        """ROS subscription callback: latch the latest Twist (linear.x, angular.z)."""
        self._latest = (float(msg.linear.x), float(msg.angular.z))
        self._last_cmd = time.monotonic()

    async def run(self) -> None:
        import rclpy

        from pibot.control.client import AgentClient

        client = AgentClient(self._agent_url, self._token)
        while rclpy.ok():
            try:
                await client.connect()
                break
            except Exception as exc:
                self._node.get_logger().warn(f"waiting for pibotd at {self._agent_url}: {exc}")
                await asyncio.sleep(2.0)
        self._node.get_logger().info(
            "pibot<->ROS2 bridge up: /cmd_vel->drive; telemetry/estop/battery/image out"
        )
        tasks = [
            asyncio.create_task(self._spin()),
            asyncio.create_task(self._drive(client)),
            asyncio.create_task(self._telemetry(client)),
        ]
        if self._video_enabled:
            tasks.append(asyncio.create_task(self._video()))
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await client.close()

    async def _spin(self) -> None:
        """Pump ROS callbacks (incl. /cmd_vel) on the asyncio loop — non-blocking spin_once."""
        import rclpy

        while rclpy.ok():
            rclpy.spin_once(self._node, timeout_sec=0.0)
            await asyncio.sleep(0.005)

    async def _drive(self, client: Any) -> None:
        """Re-send the latest /cmd_vel as a drive command at a fixed rate (deadman on staleness)."""
        import rclpy

        period = 1.0 / self._drive_rate if self._drive_rate > 0 else 0.05
        while rclpy.ok():
            v, w = self._latest
            if (time.monotonic() - self._last_cmd) > self._cmd_timeout:
                v, w = 0.0, 0.0  # stale /cmd_vel -> stop (dead teleop publisher halts the robot)
            drive = twist_to_drive(
                v, w, linear_scale=self._lin_scale, angular_scale=self._ang_scale
            )
            try:
                await client.send_command("drive", drive)
            except Exception as exc:
                self._node.get_logger().warn(f"drive send failed: {exc}; reconnecting")
                with contextlib.suppress(Exception):
                    await client.connect()
            await asyncio.sleep(period)

    async def _telemetry(self, client: Any) -> None:
        """Stream pibotd telemetry -> /pibot/telemetry, /pibot/estop, /pibot/battery."""
        import rclpy
        from sensor_msgs.msg import BatteryState
        from std_msgs.msg import Bool, String

        while rclpy.ok():
            try:
                async for snap in client.telemetry_stream():
                    self._pubs["telem"].publish(String(data=json.dumps(snap)))
                    self._pubs["estop"].publish(Bool(data=snapshot_estop(snap)))
                    volts = snapshot_battery_volts(snap)
                    if volts is not None:
                        battery = BatteryState()
                        battery.voltage = float(volts)
                        battery.present = True
                        self._pubs["battery"].publish(battery)
                    if not rclpy.ok():
                        break
            except Exception as exc:
                self._node.get_logger().warn(f"telemetry stream dropped: {exc}; retrying")
                await asyncio.sleep(1.0)

    async def _video(self) -> None:
        """Stream WS /video JPEG frames -> /pibot/image/compressed (sensor_msgs/CompressedImage)."""
        import aiohttp
        import rclpy
        from sensor_msgs.msg import CompressedImage

        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        ws_url = self._agent_url.replace("http", "ws", 1).rstrip("/") + "/video"
        while rclpy.ok():
            try:
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.ws_connect(ws_url) as ws:
                        async for msg in ws:
                            if msg.type is aiohttp.WSMsgType.BINARY:
                                image = CompressedImage()
                                image.format = "jpeg"
                                image.data = bytes(msg.data)
                                image.header.stamp = self._node.get_clock().now().to_msg()
                                image.header.frame_id = "pibot_camera"
                                self._pubs["image"].publish(image)
                            elif msg.type is not aiohttp.WSMsgType.TEXT:
                                break  # CLOSE / ERROR — reconnect
            except Exception as exc:
                self._node.get_logger().warn(f"video stream dropped: {exc}; retrying")
                await asyncio.sleep(2.0)


def main(argv: list[str] | None = None) -> int:
    """Entry point: build the ROS 2 node + publishers/subscriber and run the bridge loops."""
    import rclpy
    from geometry_msgs.msg import Twist
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import BatteryState, CompressedImage
    from std_msgs.msg import Bool, String

    rclpy.init(args=argv)
    node = rclpy.create_node("pibot_bridge")

    def param(name: str, default: Any) -> Any:
        return node.declare_parameter(name, default).value

    agent_url = str(param("agent_url", "http://127.0.0.1:8787"))
    token = str(param("agent_token", "")) or None
    drive_rate = float(param("drive_rate_hz", 20.0))
    cmd_timeout = float(param("cmd_timeout_s", 0.5))
    lin_scale = float(param("linear_scale", 1.0))
    ang_scale = float(param("angular_scale", 1.0))
    video_enabled = bool(param("video_enabled", True))

    pubs = {
        "telem": node.create_publisher(String, "pibot/telemetry", 10),
        "estop": node.create_publisher(Bool, "pibot/estop", 10),
        "battery": node.create_publisher(BatteryState, "pibot/battery", 10),
        "image": node.create_publisher(
            CompressedImage, "pibot/image/compressed", qos_profile_sensor_data
        ),
    }
    bridge = Bridge(
        node,
        pubs,
        agent_url=agent_url,
        token=token,
        drive_rate=drive_rate,
        cmd_timeout=cmd_timeout,
        lin_scale=lin_scale,
        ang_scale=ang_scale,
        video_enabled=video_enabled,
    )
    node.create_subscription(Twist, "cmd_vel", bridge.on_cmd_vel, 10)
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
