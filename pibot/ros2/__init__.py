"""ROS 2 bridge for PiBot — exposes the pibotd agent on the ROS 2 graph.

This subpackage is **optional and robot-only**: it needs ``rclpy`` (from a sourced ROS 2
install, e.g. Jazzy) which is never a dependency of the core suite. Like ``pibot.ml`` it is
loaded lazily and never imported by the CLI/agent core, so the stdlib-light suite stays free
of ROS 2. Keep this ``__init__`` import-free.

- :mod:`pibot.ros2.convert` — pure field mappings (Twist↔drive, snapshot→msgs); no rclpy,
  unit-tested in the normal gate.
- :mod:`pibot.ros2.bridge` — the ``rclpy`` node (``python -m pibot.ros2.bridge``); subscribes
  ``/cmd_vel`` → pibot ``drive`` (through the safety gate via ``AgentClient``) and publishes
  pibot telemetry / e-stop / battery / camera to ROS 2 topics.
"""
