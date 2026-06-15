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

from collections.abc import Mapping
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
