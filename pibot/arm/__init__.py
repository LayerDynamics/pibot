"""Host-side robot-arm control (SPEC: docs/plans/2026-06-13-pibot-arm-control.md).

The arm's joints are split across one or more microcontroller boards, each running
``firmware/pibot_arm_stm32`` and owning up to four channels. This package routes logical
joint commands to the right board and aggregates telemetry; kinematics/IK layer above it.
"""

from pibot.arm.kinematics import DirectSolver, JointSolver, NamedPoseSolver
from pibot.arm.manager import ArmManager, GripperState, JointRef, linear_joint_map
from pibot.arm.programs import Pose, Program, ProgramStep, record_pose
from pibot.arm.safety import ArmGate, GateResult, JointLimit
from pibot.arm.trajectory import TrajectoryFrame, cartesian_trajectory, joint_trajectory

__all__ = [
    "ArmGate",
    "ArmManager",
    "DirectSolver",
    "GateResult",
    "GripperState",
    "JointLimit",
    "JointRef",
    "JointSolver",
    "NamedPoseSolver",
    "Pose",
    "Program",
    "ProgramStep",
    "TrajectoryFrame",
    "cartesian_trajectory",
    "joint_trajectory",
    "linear_joint_map",
    "record_pose",
]
