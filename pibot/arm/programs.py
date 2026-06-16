"""Teach/playback pose + program model (M-ARM-5)."""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any


def _coerce_joints(raw: Mapping[Any, Any]) -> dict[int, float]:
    return {int(joint): float(deg) for joint, deg in raw.items()}


@dataclass(frozen=True)
class Pose:
    """A named, persistent arm pose recorded from telemetry."""

    name: str
    joints: dict[int, float]
    gripper: float | None = None
    tool: bool | None = None
    cartesian: dict[str, float] | None = None
    created: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "joints": {str(joint): deg for joint, deg in sorted(self.joints.items())},
            "created": self.created,
        }
        if self.gripper is not None:
            data["gripper"] = self.gripper
        if self.tool is not None:
            data["tool"] = self.tool
        if self.cartesian is not None:
            data["cartesian"] = dict(self.cartesian)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Pose:
        name = str(data["name"]).strip()
        if not name:
            raise ValueError("pose name must be non-empty")
        joints = _coerce_joints(data["joints"])
        cartesian = data.get("cartesian")
        return cls(
            name=name,
            joints=joints,
            gripper=None if data.get("gripper") is None else float(data["gripper"]),
            tool=None if data.get("tool") is None else bool(data["tool"]),
            cartesian=(
                None if cartesian is None else {str(k): float(v) for k, v in cartesian.items()}
            ),
            created=float(data.get("created", time.time())),
        )


def record_pose(name: str, snapshot: Mapping[str, Any], *, created: float | None = None) -> Pose:
    """Record a named pose from an arm telemetry snapshot."""

    positions = snapshot.get("positions")
    if not isinstance(positions, Mapping) or not positions:
        raise ValueError("telemetry snapshot has no positions to record")
    gripper = snapshot.get("gripper")
    pose = snapshot.get("pose")
    return Pose(
        name=name,
        joints=_coerce_joints(positions),
        gripper=None if not isinstance(gripper, Mapping) else float(gripper.get("deg", 0.0)),
        tool=None if not isinstance(gripper, Mapping) else bool(gripper.get("tool", False)),
        cartesian=(
            None if not isinstance(pose, Mapping) else {str(k): float(v) for k, v in pose.items()}
        ),
        created=time.time() if created is None else created,
    )


@dataclass(frozen=True)
class ProgramStep:
    """One teach/playback program step."""

    kind: str
    pose: str | None = None
    seconds: float | None = None
    deg: float | None = None
    on: bool | None = None
    count: int | None = None
    steps: tuple[ProgramStep, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"kind": self.kind}
        if self.pose is not None:
            data["pose"] = self.pose
        if self.seconds is not None:
            data["seconds"] = self.seconds
        if self.deg is not None:
            data["deg"] = self.deg
        if self.on is not None:
            data["on"] = self.on
        if self.count is not None:
            data["count"] = self.count
        if self.steps:
            data["steps"] = [step.as_dict() for step in self.steps]
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProgramStep:
        kind = str(data.get("kind", "")).strip()
        if kind not in {"moveJ", "moveL", "grip", "tool", "wait", "loop"}:
            raise ValueError(f"unknown step kind {kind!r}")

        if kind in {"moveJ", "moveL"}:
            pose = data.get("pose")
            if not isinstance(pose, str) or not pose.strip():
                raise ValueError(f"{kind} step needs a pose name")
            seconds = float(data.get("seconds", 2.0))
            if seconds <= 0.0:
                raise ValueError(f"{kind} step seconds must be positive")
            return cls(kind=kind, pose=pose, seconds=seconds)

        if kind == "grip":
            if "deg" not in data:
                raise ValueError("grip step needs deg")
            return cls(kind=kind, deg=float(data["deg"]))

        if kind == "tool":
            if "on" not in data:
                raise ValueError("tool step needs on")
            return cls(kind=kind, on=bool(data["on"]))

        if kind == "wait":
            seconds = float(data.get("seconds", 0.0))
            if seconds <= 0.0:
                raise ValueError("wait step seconds must be positive")
            return cls(kind=kind, seconds=seconds)

        count = int(data.get("count", 0))
        raw_steps = data.get("steps")
        if count <= 0:
            raise ValueError("loop step count must be positive")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("loop step needs nested steps")
        return cls(
            kind=kind,
            count=count,
            steps=tuple(cls.from_dict(step) for step in raw_steps),
        )


@dataclass(frozen=True)
class Program:
    """A named arm playback program."""

    name: str
    steps: tuple[ProgramStep, ...]
    created: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "steps": [step.as_dict() for step in self.steps],
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Program:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("program name must be non-empty")
        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("program steps must be a non-empty list")
        return cls(
            name=name,
            steps=tuple(ProgramStep.from_dict(step) for step in raw_steps),
            created=float(data.get("created", time.time())),
        )

    def expanded_steps(self) -> Iterator[ProgramStep]:
        for step in self.steps:
            yield from _expand_step(step)


def _expand_step(step: ProgramStep) -> Iterator[ProgramStep]:
    if step.kind != "loop":
        yield step
        return
    assert step.count is not None
    for _ in range(step.count):
        for inner in step.steps:
            yield from _expand_step(inner)
