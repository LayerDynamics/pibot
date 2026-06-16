"""Motion-intent layer for the arm — the swappable solver seam above ``ArmManager``.

A :class:`JointSolver` turns some higher-level *intent* into per-joint angle targets
(logical joint id → degrees) that ``ArmManager.move_synchronized`` then executes. This is the
modular boundary the plan calls for (docs/plans/2026-06-13-pibot-arm-control.md): the firmware and
``ArmManager`` never change as the solver evolves.

Shipped here:
  - :class:`DirectSolver`   — the intent *is* joint angles (range-validated pass-through).
  - :class:`NamedPoseSolver`— a registry of preset arm configurations ("home", "ready", …).
  - :class:`IKSolver`       — Cartesian end-effector :class:`Pose` → joint angles (M-ARM-4), numeric
    inverse kinematics over the in-tree geometry model. It drops into this exact interface, so a
    Cartesian intent reaches ``ArmManager.move_synchronized`` with no firmware or manager change.

:class:`ForwardKinematics` (joint angles → :class:`Pose`) lives here too. Both kinematics classes
need the in-tree geometry (link lengths / joint limits) and **lazy-import** ikpy + numpy from the
optional ``pibot[arm-ik]`` extra — importing this module stays numpy-free (NFR-2).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

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


def _build_chain(model: object | None) -> tuple[Any, int]:
    """Load the in-tree geometry model into an ``ikpy.chain.Chain`` (lazy ikpy + numpy) and return
    ``(chain, num_logical_joints)``. Shared by :class:`ForwardKinematics` and :class:`IKSolver`.

    The active-links mask treats only the arm joints as actuated (fixed base + n joints + tool); the
    layout is validated so an extra fixed link (mount/sensor) can't silently mis-align the chain.
    """
    from ikpy.chain import Chain  # lazy: needs the `[arm-ik]` extra

    from pibot.arm import geometry

    loaded = model if model is not None else geometry.load()
    n = len(loaded.joints)  # type: ignore[attr-defined]
    mask = [False] + [True] * n + [False]
    chain = Chain.from_urdf_file(
        str(loaded.urdf_path),  # type: ignore[attr-defined]
        active_links_mask=mask,
    )
    if len(chain.links) != n + 2:
        raise ValueError(
            f"incompatible URDF chain: expected {n + 2} links "
            f"(fixed base + {n} joints + tool), got {len(chain.links)}"
        )
    return chain, n


class ForwardKinematics:
    """Joint angles → end-effector :class:`Pose` via the in-tree geometry model and an ikpy chain.

    Loads ``pibot.arm.geometry``'s URDF into an ``ikpy.chain.Chain`` once at construction (ikpy +
    numpy imported lazily here). :meth:`solve` maps PiBot logical joint ids (degrees) to the chain's
    radian inputs — joints absent from the input default to 0°.
    """

    def __init__(self, model: object | None = None) -> None:
        self._chain, self._n = _build_chain(model)

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


# ---- Inverse kinematics (M-ARM-4) ----------------------------------------------------------------


class IKError(ValueError):
    """IK could not produce a valid joint solution for the requested pose (unreachable / singular /
    a joint would exceed its limit). A subclass of ``ValueError`` so existing intent-validation
    callers catch it, while letting IK-specific handling distinguish it when useful."""


def _matrix_from_rpy(rx: float, ry: float, rz: float) -> list[list[float]]:
    """Rotation matrix ``Rz(rz)·Ry(ry)·Rx(rx)`` (XYZ fixed-axis) — the inverse of
    :func:`_rpy_from_matrix`. Pure stdlib (no numpy) so only :meth:`IKSolver.solve` pulls numpy."""
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return [
        [cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
        [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
        [-sy, cy * sx, cy * cx],
    ]


class IKSolver:
    """Cartesian end-effector :class:`Pose` → per-joint angle targets (logical joint id → degrees).

    Numeric inverse kinematics over the in-tree geometry model via an ikpy chain (ikpy + numpy
    lazy-imported, so the arm core stays numpy-free — NFR-2). Implements the :class:`JointSolver`
    seam: an IK target drops straight into ``ArmManager.move_synchronized``, no manager/firmware
    change.

    A solved configuration is **rejected** (:class:`IKError`) when the achieved pose misses the
    request beyond tolerance (unreachable / singular) or any joint would exceed its URDF limit — IK
    never emits motor targets that don't reach the goal or that violate a joint limit (SPEC R5).
    """

    def __init__(
        self,
        model: object | None = None,
        *,
        position_tol_m: float = 3e-3,
        orientation_tol_rad: float = 3e-2,
    ) -> None:
        self._chain, self._n = _build_chain(model)
        self._pos_tol = float(position_tol_m)
        self._ori_tol = float(orientation_tol_rad)

    @property
    def num_joints(self) -> int:
        return self._n

    def solve(self, target: Pose) -> dict[int, float]:
        """Inverse kinematics for a target end-effector :class:`Pose` → ``{joint id: degrees}``.

        Solves position **and** orientation from a neutral (all-zero) seed, then verifies the
        achieved pose and joint limits before returning — a miss raises :class:`IKError`.
        """
        import numpy as np  # lazy: ikpy already pulls numpy; the boundary is module *import*

        target_orientation = np.array(_matrix_from_rpy(target.rx, target.ry, target.rz))
        target_position = [target.x, target.y, target.z]
        solution = self._chain.inverse_kinematics(
            target_position=target_position,
            target_orientation=target_orientation,
            orientation_mode="all",
        )

        # Reachability: the solution's FK pose must match the request within tolerance — ikpy
        # returns a best-effort projection for unreachable/singular targets, which we reject here.
        achieved = np.asarray(self._chain.forward_kinematics(solution))
        pos_err = float(np.linalg.norm(achieved[:3, 3] - np.asarray(target_position)))
        cos_angle = (float(np.trace(target_orientation.T @ achieved[:3, :3])) - 1.0) / 2.0
        ori_err = math.acos(max(-1.0, min(1.0, cos_angle)))
        if pos_err > self._pos_tol or ori_err > self._ori_tol:
            raise IKError(
                f"pose unreachable: position error {pos_err * 1000:.1f} mm / orientation error "
                f"{math.degrees(ori_err):.1f}° exceed tolerances "
                f"({self._pos_tol * 1000:.1f} mm / {math.degrees(self._ori_tol):.1f}°)"
            )

        # Joint-limit guard (SPEC R5): ikpy bounds the solve, but never emit an out-of-limit target.
        targets: dict[int, float] = {}
        for i in range(self._n):
            angle = float(solution[1 + i])
            lower, upper = self._chain.links[1 + i].bounds
            if angle < lower - 1e-4 or angle > upper + 1e-4:
                raise IKError(
                    f"joint {i} solution {math.degrees(angle):.1f}° outside limit "
                    f"[{math.degrees(lower):.1f}°, {math.degrees(upper):.1f}°]"
                )
            targets[i] = math.degrees(angle)
        return targets
