"""Host-side robot-arm control (SPEC: docs/plans/2026-06-13-pibot-arm-control.md).

The arm's joints are split across one or more microcontroller boards, each running
``firmware/pibot_arm_stm32`` and owning up to four channels. This package routes logical
joint commands to the right board and aggregates telemetry; kinematics/IK layer above it.
"""

from pibot.arm.manager import ArmManager, JointRef, linear_joint_map

__all__ = ["ArmManager", "JointRef", "linear_joint_map"]
