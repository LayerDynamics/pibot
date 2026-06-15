"""ArmManager — route logical joint commands across the per-board controllers.

Each board (``firmware/pibot_arm_stm32``) owns up to four stepper *channels* and speaks the
PiBot CRC protocol over its own serial link. ``ArmManager`` maps each **logical** joint id to a
``(board, channel)`` location, encodes the joint protocol (``jpos``/``jvel``/``jstop``/``home``/
``estop``/``enable``), and sends each command to the owning board's transport. It also drains each
board's ``joints`` telemetry and re-keys it by logical joint.

This layer is **pure routing + I/O** — no kinematics. Coordination/trajectories (A.4) and IK (A.5)
plug in *above* it without changing the firmware contract.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from pibot.protocol.codec import (
    DecodeError,
    Message,
    MessageType,
    SeqTracker,
    decode,
    encode,
)
from pibot.transport.base import Transport


@dataclass(frozen=True)
class JointRef:
    """A logical joint's physical home: which ``board`` it's on, and the firmware ``channel``."""

    board: int
    channel: int


def linear_joint_map(per_board: list[int]) -> list[JointRef]:
    """Build a sequential logical→physical map: ``per_board=[3, 3]`` → J0..J2 on board 0, J3..J5 on
    board 1. Matches the plan's 3+3 split across two 4.2.2 boards."""
    joints: list[JointRef] = []
    for board, count in enumerate(per_board):
        for channel in range(count):
            joints.append(JointRef(board=board, channel=channel))
    return joints


class ArmManager:
    """Route joint commands to the boards that own them; aggregate joint telemetry."""

    def __init__(
        self,
        transports: list[Transport],
        joints: list[JointRef],
        *,
        encoding: str = "ascii",
    ) -> None:
        if any(j.board >= len(transports) for j in joints):
            raise ValueError("a joint references a board with no transport")
        self._t = transports
        self._joints = joints
        self._encoding = encoding
        self._seq = [SeqTracker() for _ in transports]  # independent sequence per board

    @property
    def num_joints(self) -> int:
        return len(self._joints)

    # ---- lifecycle --------------------------------------------------------------------------
    def open(self) -> None:
        """Open every board's transport. On partial failure, close what opened and re-raise."""
        opened: list[Transport] = []
        try:
            for t in self._t:
                t.open()
                opened.append(t)
        except Exception:
            for t in opened:
                with contextlib.suppress(Exception):
                    t.close()
            raise

    def close(self) -> None:
        """Close every board's transport (best-effort; one failure doesn't skip the rest)."""
        for t in self._t:
            with contextlib.suppress(Exception):
                t.close()

    # ---- command routing --------------------------------------------------------------------
    def _send(self, board: int, name: str, args: dict[str, float]) -> None:
        seq = self._seq[board].next()
        self._t[board].send(encode(Message(MessageType.COMMAND, seq, name, args), self._encoding))

    def _joint_send(self, joint: int, name: str, args: dict[str, float]) -> None:
        ref = self._joints[joint]
        self._send(ref.board, name, {"id": ref.channel, **args})

    def jpos(self, joint: int, deg: float) -> None:
        """Move a joint to an absolute angle (degrees) at its configured speed."""
        self._joint_send(joint, "jpos", {"deg": float(deg)})

    def jmove(self, joint: int, deg: float, dps: float) -> None:
        """Move a joint to an absolute angle at a specific speed (deg/sec). The board clamps the
        speed to the joint's max. Building block for :meth:`move_synchronized`."""
        self._joint_send(joint, "jmove", {"deg": float(deg), "dps": float(dps)})

    def move_synchronized(
        self, targets: dict[int, float], current: dict[int, float], seconds: float
    ) -> None:
        """Move several joints so they all **arrive together** after ``seconds``.

        Each joint's speed is scaled to its travel distance — ``dps = |target - current| / seconds``
        — so the joint with the farthest to go sets the pace and the rest move slower to match.
        ``current`` is the latest angle per joint (e.g. from :meth:`positions`). If a required speed
        exceeds a joint's firmware max it is clamped on-board (that joint lags); keep ``seconds``
        feasible for exact synchrony.
        """
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        for joint, target in targets.items():
            if joint not in current:
                raise KeyError(f"no current position for joint {joint}")
            dps = abs(float(target) - float(current[joint])) / seconds
            self.jmove(joint, target, dps)

    def jvel(self, joint: int, dps: float) -> None:
        """Jog a joint at a velocity (deg/sec); 0 stops it."""
        self._joint_send(joint, "jvel", {"dps": float(dps)})

    def jstop(self, joint: int) -> None:
        """Stop one joint, holding position."""
        self._joint_send(joint, "jstop", {})

    def home(self, joint: int) -> None:
        """Home one joint against its endstop."""
        self._joint_send(joint, "home", {})

    # ---- whole-arm safety (broadcast to every board) ----------------------------------------
    def estop(self) -> None:
        """Latch e-stop on **every** board (all motion halts, refused until cleared)."""
        for board in range(len(self._t)):
            self._send(board, "estop", {})

    def clear_estop(self) -> None:
        """Clear the e-stop latch on every board (firmware resumes on ``set,<_>,0``)."""
        for board in range(len(self._t)):
            self._send(board, "set", {"param": 0, "value": 0})

    def enable(self, on: bool) -> None:
        """Energize (``True``) or release (``False``) the steppers on every board."""
        for board in range(len(self._t)):
            self._send(board, "enable", {"on": 1 if on else 0})

    # ---- telemetry --------------------------------------------------------------------------
    def positions(self, timeout: float = 0.2) -> dict[int, float]:
        """Return the latest angle (deg) per logical joint, drained from each board's telemetry.

        Reads the freshest ``joints`` frame from every board (blocking up to ``timeout`` for the
        first frame on each, then draining), and re-keys ``(board, channel)`` → logical joint id.
        Joints with no telemetry yet are simply absent from the result.
        """
        board_pos: dict[int, list[float]] = {}
        for board, transport in enumerate(self._t):
            frame = transport.recv(timeout)
            while frame is not None:
                try:
                    msg = decode(frame, self._encoding)
                except DecodeError:
                    frame = transport.recv(0.0)
                    continue
                if msg.type is MessageType.TELEMETRY and msg.name == "joints":
                    board_pos[board] = [float(v) for v in msg.args.values()]
                frame = transport.recv(0.0)  # drain remaining buffered frames

        out: dict[int, float] = {}
        for jid, ref in enumerate(self._joints):
            vals = board_pos.get(ref.board)
            if vals is not None and ref.channel < len(vals):
                out[jid] = vals[ref.channel]
        return out
