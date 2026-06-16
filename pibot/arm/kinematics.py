"""Motion-intent layer for the arm — the swappable solver seam above ``ArmManager``.

A :class:`JointSolver` turns some higher-level *intent* into per-joint angle targets
(logical joint id → degrees) that ``ArmManager.move_synchronized`` then executes. This is the
modular boundary the plan calls for (docs/plans/2026-06-13-pibot-arm-control.md): the firmware and
``ArmManager`` never change as the solver evolves.

Shipped here, both fully usable today:
  - :class:`DirectSolver`   — the intent *is* joint angles (range-validated pass-through).
  - :class:`NamedPoseSolver`— a registry of preset arm configurations ("home", "ready", …).

An ``IKSolver`` (Cartesian gripper pose → joint angles) is intentionally **not** here: it requires
the arm's link geometry (link lengths / DH parameters), which is hardware-specific. It drops into
this exact interface once that geometry is known — no firmware or manager change.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, TypeVar

_Intent = TypeVar("_Intent", contravariant=True)


class JointSolver(Protocol[_Intent]):
    """Turn a motion intent into per-joint angle targets (logical joint id → degrees)."""

    def solve(self, target: _Intent) -> dict[int, float]: ...


class DirectSolver:
    """The intent is already joint angles; validate the joint ids and pass them through.

    This is the base case (no kinematics) and the contract every richer solver shares: produce a
    ``{joint_id: degrees}`` map for ``ArmManager.move_synchronized``.
    """

    def __init__(self, num_joints: int) -> None:
        self._n = num_joints

    def solve(self, target: Mapping[int, float]) -> dict[int, float]:
        out: dict[int, float] = {}
        for joint, deg in target.items():
            if not 0 <= joint < self._n:
                raise ValueError(f"joint {joint} out of range [0, {self._n})")
            out[joint] = float(deg)
        return out


class NamedPoseSolver:
    """Resolve a named arm pose ("home", "ready", "stow", …) to its preset joint angles."""

    def __init__(self, poses: Mapping[str, Mapping[int, float]]) -> None:
        self._poses: dict[str, dict[int, float]] = {
            name: {int(j): float(d) for j, d in angles.items()} for name, angles in poses.items()
        }

    @property
    def names(self) -> list[str]:
        """The registered pose names, sorted."""
        return sorted(self._poses)

    def solve(self, target: str) -> dict[int, float]:
        try:
            return dict(self._poses[target])
        except KeyError as exc:
            raise KeyError(f"unknown pose {target!r}; known: {self.names}") from exc


# ---- Forward kinematics (M-ARM-3) ----------------------------------------------------------------
# The numeric solver (ikpy + numpy) is **lazy-imported** inside the methods below so that importing
# this module stays numpy-free (NFR-2). FK needs the optional ``pibot[arm-ik]`` extra installed.


@dataclass(frozen=True)
class Pose:
    """End-effector pose: position (m) + orientation as roll/pitch/yaw (XYZ fixed-axis) radians."""

    x: float
    y: float
    z: float
    rx: float
    ry: float
    rz: float

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z, "rx": self.rx, "ry": self.ry, "rz": self.rz}


def _rpy_from_matrix(m: object) -> tuple[float, float, float]:
    """Extract roll/pitch/yaw (XYZ fixed-axis) from a 4x4 homogeneous transform's rotation block."""

    def at(i: int, j: int) -> float:
        return float(m[i][j])  # type: ignore[index]  # numpy array or nested sequence

    sy = math.hypot(at(0, 0), at(1, 0))
    if sy > 1e-6:
        return (
            math.atan2(at(2, 1), at(2, 2)),
            math.atan2(-at(2, 0), sy),
            math.atan2(at(1, 0), at(0, 0)),
        )
    return math.atan2(-at(1, 2), at(1, 1)), math.atan2(-at(2, 0), sy), 0.0


class ForwardKinematics:
    """Joint angles → end-effector :class:`Pose` via the in-tree geometry model and an ikpy chain.

    Loads ``pibot.arm.geometry``'s URDF into an ``ikpy.chain.Chain`` once at construction (ikpy +
    numpy imported lazily here). :meth:`solve` maps PiBot logical joint ids (degrees) to the chain's
    radian inputs — joints absent from the input default to 0°.
    """

    def __init__(self, model: object | None = None) -> None:
        from ikpy.chain import Chain  # lazy: needs the `[arm-ik]` extra

        from pibot.arm import geometry

        loaded = model if model is not None else geometry.load()
        self._n = len(loaded.joints)  # type: ignore[attr-defined]
        # Mask the fixed base + tool links so ikpy doesn't warn/treat them as actuated.
        mask = [False] + [True] * self._n + [False]
        self._chain = Chain.from_urdf_file(str(loaded.urdf_path), active_links_mask=mask)  # type: ignore[attr-defined]

    @property
    def num_joints(self) -> int:
        return self._n

    def solve(self, joint_angles_deg: Mapping[int, float]) -> Pose:
        """Forward kinematics for ``{logical joint id: degrees}`` → end-effector :class:`Pose`."""
        angles = [0.0] * len(self._chain.links)
        for i in range(self._n):
            angles[1 + i] = math.radians(float(joint_angles_deg.get(i, 0.0)))
        m = self._chain.forward_kinematics(angles)
        return Pose(float(m[0][3]), float(m[1][3]), float(m[2][3]), *_rpy_from_matrix(m))
