"""Host-side arm safety gate — the per-joint analogue of :mod:`pibot.control.safety`.

Three guards stand between an arm-motion frame and the boards, *in addition to* the firmware's
own (independent) safety:

* **range** — the logical joint id must address a configured joint;
* **clamp** — absolute angles are bounded to the joint's ``[min_deg, max_deg]`` and velocities to
  ``±max_dps`` before they leave the host;
* **latch / homing** — every motion command is refused while e-stop is latched, and absolute
  moves (``jpos``/``jmove``/``move``) are refused until the joint has been homed.

The validators are **pure**: the mutable latch + homed state is passed in by the caller (the
agent owns the live state on ``AgentState``), so this module imports nothing but the stdlib and
keeps the ``pibot.arm`` core / CLI / ``agent`` stdlib-light (NFR-2). The firmware remains the
final arbiter — it enforces its own soft limits, latched e-stop and homing-before-``jpos`` even
if this gate is bypassed (NFR-1).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# Permissive-but-bounded defaults when no per-joint limits are configured. The firmware's tuned
# per-joint ``JCFG`` soft limits still apply on-board; this is only the coarse host-side bound.
DEFAULT_MIN_DEG = -180.0
DEFAULT_MAX_DEG = 180.0
DEFAULT_MAX_DPS = 90.0

# Servo gripper physical range (M-ARM-2). The host gate clamps to this coarse bound; the firmware
# further clamps to the configured per-gripper ``[GRIP_MIN_DEG, GRIP_MAX_DEG]``.
SERVO_MIN_DEG = 0.0
SERVO_MAX_DEG = 180.0


@dataclass(frozen=True)
class JointLimit:
    """Per-logical-joint motion bounds enforced by the host gate."""

    min_deg: float = DEFAULT_MIN_DEG
    max_deg: float = DEFAULT_MAX_DEG
    max_dps: float = DEFAULT_MAX_DPS


@dataclass(frozen=True)
class GateResult:
    """The gate's verdict for one frame.

    ``ok`` accepts; ``args`` carries the clamped scalar arguments (``deg``/``dps``) and
    ``targets`` the clamped per-joint angles for a synchronized ``move``. ``reason`` is the
    nak text when refused.
    """

    ok: bool
    reason: str = ""
    args: Mapping[str, float] = field(default_factory=dict)
    targets: Mapping[int, float] = field(default_factory=dict)


def _bound(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class ArmGate:
    """Validate + clamp arm-motion frames against per-joint limits and live latch/homed state."""

    def __init__(self, limits: Sequence[JointLimit]) -> None:
        self._limits = list(limits)

    @classmethod
    def with_defaults(cls, num_joints: int) -> ArmGate:
        """A gate with one permissive default limit per joint (used when none are configured)."""
        return cls([JointLimit() for _ in range(num_joints)])

    @property
    def num_joints(self) -> int:
        return len(self._limits)

    def limit(self, joint: int) -> JointLimit:
        """The configured limit for a logical joint (caller ensures the id is in range)."""
        return self._limits[joint]

    # ---- per-command validators ---------------------------------------------------------

    def jpos(self, joint: int, deg: float, *, estopped: bool, homed: set[int]) -> GateResult:
        """Absolute move at the joint's configured speed: range + estop + homing, angle clamped."""
        guard = self._guard_motion(joint, estopped)
        if guard is not None:
            return guard
        if joint not in homed:
            return GateResult(False, f"joint {joint} not homed")
        lim = self._limits[joint]
        return GateResult(True, args={"deg": _bound(float(deg), lim.min_deg, lim.max_deg)})

    def jmove(
        self, joint: int, deg: float, dps: float, *, estopped: bool, homed: set[int]
    ) -> GateResult:
        """Absolute move at a specific speed: like :meth:`jpos`, plus the speed clamped to max."""
        guard = self._guard_motion(joint, estopped)
        if guard is not None:
            return guard
        if joint not in homed:
            return GateResult(False, f"joint {joint} not homed")
        lim = self._limits[joint]
        return GateResult(
            True,
            args={
                "deg": _bound(float(deg), lim.min_deg, lim.max_deg),
                "dps": _bound(float(dps), 0.0, lim.max_dps),
            },
        )

    def jvel(self, joint: int, dps: float, *, estopped: bool) -> GateResult:
        """Velocity jog: range + estop, magnitude clamped to ``±max_dps``. No homing required."""
        guard = self._guard_motion(joint, estopped)
        if guard is not None:
            return guard
        lim = self._limits[joint]
        return GateResult(True, args={"dps": _bound(float(dps), -lim.max_dps, lim.max_dps)})

    def jstop(self, joint: int) -> GateResult:
        """Stop one joint — always permitted (it reduces motion), even while e-stop is latched."""
        bad = self._check_joint(joint)
        if bad is not None:
            return GateResult(False, bad)
        return GateResult(True)

    def grip(self, deg: float, *, estopped: bool) -> GateResult:
        """Servo gripper: refused while e-stop is latched; the angle is clamped to the servo's
        physical range (the firmware further clamps to the configured gripper limits)."""
        if estopped:
            return GateResult(False, "estop latched")
        return GateResult(True, args={"deg": _bound(float(deg), SERVO_MIN_DEG, SERVO_MAX_DEG)})

    def tool(self, *, estopped: bool) -> GateResult:
        """Digital-output tool (relay/pneumatic): refused while e-stop is latched."""
        if estopped:
            return GateResult(False, "estop latched")
        return GateResult(True)

    def home(self, joint: int, *, estopped: bool) -> GateResult:
        """Home one joint: range + estop. Does not require prior homing (it establishes it)."""
        guard = self._guard_motion(joint, estopped)
        if guard is not None:
            return guard
        return GateResult(True)

    def move(
        self,
        targets: Mapping[int, float],
        current: Mapping[int, float],
        seconds: float,
        *,
        estopped: bool,
        homed: set[int],
    ) -> GateResult:
        """Synchronized multi-joint arrival: every target ranged, homed, has telemetry; angles
        clamped. The per-joint *speed* is derived by :meth:`ArmManager.move_synchronized` from the
        travel distance and clamped on-board, so only the angles are bounded here."""
        if estopped:
            return GateResult(False, "estop latched")
        if seconds <= 0:
            return GateResult(False, "seconds must be positive")
        clamped: dict[int, float] = {}
        for joint, deg in targets.items():
            bad = self._check_joint(joint)
            if bad is not None:
                return GateResult(False, bad)
            if joint not in homed:
                return GateResult(False, f"joint {joint} not homed")
            if joint not in current:
                return GateResult(False, f"no telemetry for joint {joint}")
            lim = self._limits[joint]
            clamped[joint] = _bound(float(deg), lim.min_deg, lim.max_deg)
        return GateResult(True, targets=clamped)

    # ---- internals ----------------------------------------------------------------------

    def _guard_motion(self, joint: int, estopped: bool) -> GateResult | None:
        bad = self._check_joint(joint)
        if bad is not None:
            return GateResult(False, bad)
        if estopped:
            return GateResult(False, "estop latched")
        return None

    def _check_joint(self, joint: int) -> str | None:
        if not 0 <= joint < len(self._limits):
            return f"joint {joint} out of range [0,{len(self._limits)})"
        return None
