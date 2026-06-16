"""Task #13 — pibotd arm telemetry: GET /arm/telemetry + the drain loop + build_arm wiring.

The agent owns the ArmManager (the layered topology): a single background drain task is the sole
reader of the arm boards' telemetry, so concurrent reads hit a cache instead of racing on recv.
No hardware — a fake transport replays a fixed ``joints`` frame.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from agent.app import build_app
from agent.pibotd import build_arm, build_arm_gate
from pibot.arm import ArmManager, linear_joint_map
from pibot.config import Config
from pibot.errors import UsageError
from pibot.protocol.codec import Message, MessageType, decode, encode
from pibot.transport.base import Transport
from pibot.transport.responder import ResponderTransport


def _run(coro: Any) -> None:
    asyncio.run(coro)


class FakeArmTransport(Transport):
    """One arm board: replays a fixed ``joints`` frame on each blocking recv, nothing to drain."""

    def __init__(self, positions: list[float]) -> None:
        self._positions = positions
        self._open = False
        self.open_calls = 0
        self.close_calls = 0

    def open(self) -> None:
        self._open = True
        self.open_calls += 1

    def close(self) -> None:
        self._open = False
        self.close_calls += 1

    def send(self, frame: bytes) -> None:
        pass

    def recv(self, timeout: float) -> bytes | None:
        if timeout <= 0:
            return None  # a drain pass — nothing buffered behind the first frame
        time.sleep(0.005)  # mimic the board's cadence so the drain loop self-paces
        args = {f"j{i}": p for i, p in enumerate(self._positions)}
        return encode(Message(MessageType.TELEMETRY, 0, "joints", args), "ascii")

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def info(self) -> dict[str, Any]:
        return {"backend": "fake-arm"}


class RecordingArmTransport(FakeArmTransport):
    """A fake board that also records every command frame the host sends, decoded."""

    def __init__(self, positions: list[float]) -> None:
        super().__init__(positions)
        self.sent: list[Message] = []

    def send(self, frame: bytes) -> None:
        self.sent.append(decode(frame, "ascii"))

    def names(self) -> list[str]:
        return [m.name for m in self.sent]


class GripperArmTransport(FakeArmTransport):
    """Replays a ``joints`` frame on each blocking recv, then a ``grip`` frame on the drain pass."""

    def __init__(self, positions: list[float], grip_deg: float, tool: float) -> None:
        super().__init__(positions)
        self._grip = (grip_deg, tool)
        self._emit_grip = False

    def recv(self, timeout: float) -> bytes | None:
        if timeout <= 0:
            if self._emit_grip:
                self._emit_grip = False
                return encode(
                    Message(
                        MessageType.TELEMETRY,
                        0,
                        "grip",
                        {"deg": self._grip[0], "tool": self._grip[1]},
                    ),
                    "ascii",
                )
            return None
        self._emit_grip = True
        return super().recv(timeout)


class OnceThenSilentArmTransport(FakeArmTransport):
    """A board that reports its joints frame exactly once, then never again — to model a board
    that drops out of a drain cycle while another board keeps reporting."""

    def __init__(self, positions: list[float]) -> None:
        super().__init__(positions)
        self._reported = False

    def recv(self, timeout: float) -> bytes | None:
        if timeout <= 0 or self._reported:
            time.sleep(0.005)
            return None
        self._reported = True
        return super().recv(timeout)


def test_arm_telemetry_disabled_when_no_arm() -> None:
    async def body() -> None:
        app = build_app(transport=ResponderTransport(), trust_loopback=True)
        async with TestClient(TestServer(app)) as c:
            d = await (await c.get("/arm/telemetry")).json()
            assert d["ok"] is True
            assert d["enabled"] is False
            assert d["num_joints"] == 0
            assert d["positions"] == {}
            assert d["age_ms"] is None
            assert d["homed"] == {}
            assert d["estopped"] is False
            assert d["gripper"] is None
            assert d["pose"] is None

    _run(body())


def test_arm_telemetry_streams_positions_through_drain() -> None:
    async def body() -> None:
        fake = FakeArmTransport([10.0, 20.0, 30.0])
        arm = ArmManager([fake], linear_joint_map([3]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            # The drain task fills the cache asynchronously after startup; poll until it has.
            positions: dict[str, float] = {}
            for _ in range(40):
                d = await (await c.get("/arm/telemetry")).json()
                if d["positions"]:
                    positions = d["positions"]
                    assert d["enabled"] is True
                    assert d["num_joints"] == 3
                    assert isinstance(d["age_ms"], (int, float))
                    break
                await asyncio.sleep(0.02)
            assert positions == {"0": 10.0, "1": 20.0, "2": 30.0}
        # Cleanup stopped the drain loop and closed the board's transport.
        assert fake.close_calls >= 1
        assert not fake.is_open

    _run(body())


def test_arm_telemetry_drain_merges_per_board_and_keeps_silent_board_angles() -> None:
    """A board that stops reporting must NOT lose its joints from the cache: the drain merges
    per-board updates instead of overwriting the whole positions dict."""

    async def body() -> None:
        board_a = FakeArmTransport([10.0, 20.0, 30.0])  # joints 0,1,2 — reports every cycle
        board_b = OnceThenSilentArmTransport([40.0, 50.0, 60.0])  # joints 3,4,5 — reports once
        arm = ArmManager([board_a, board_b], linear_joint_map([3, 3]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            # Wait until board B has been drained at least once (all six joints present).
            for _ in range(60):
                d = await (await c.get("/arm/telemetry")).json()
                if {"3", "4", "5"} <= set(d["positions"]):
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("board B never reported")

            # Let many more drain cycles run with board B silent, then confirm its angles persist.
            await asyncio.sleep(0.3)
            d = await (await c.get("/arm/telemetry")).json()
            assert d["positions"]["3"] == 40.0
            assert d["positions"]["4"] == 50.0
            assert d["positions"]["5"] == 60.0
            # Board A is still live.
            assert d["positions"]["0"] == 10.0

    _run(body())


def test_arm_transport_opened_on_startup_closed_on_cleanup() -> None:
    async def body() -> None:
        fake = FakeArmTransport([1.0])
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)):
            assert fake.open_calls >= 1
            assert fake.is_open
        assert not fake.is_open  # closed on cleanup

    _run(body())


def test_arm_open_failure_does_not_take_down_the_control_plane() -> None:
    """An unplugged arm board at boot must NOT abort pibotd startup — /estop must stay up."""

    async def body() -> None:
        class FailingOpenArmTransport(FakeArmTransport):
            def open(self) -> None:
                raise OSError("arm board not connected")

        arm = ArmManager([FailingOpenArmTransport([1.0])], linear_joint_map([1]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            # The control plane is still serving — the safety path survived the arm failure.
            assert (await c.post("/estop")).status == 200
            # The arm degraded to "disabled" instead of killing the agent.
            d = await (await c.get("/arm/telemetry")).json()
            assert d["enabled"] is False

    _run(body())


def test_build_arm_none_when_no_ports() -> None:
    assert build_arm(Config()) is None


def test_build_arm_length_mismatch_raises() -> None:
    cfg = Config(arm_serial_ports=["/dev/ttyUSB0"], arm_joints_per_board=[3, 3])
    with pytest.raises(UsageError):
        build_arm(cfg)


def test_build_arm_builds_manager_from_config() -> None:
    cfg = Config(
        arm_serial_ports=["/dev/ttyUSB0", "/dev/ttyUSB1"],
        arm_joints_per_board=[3, 3],
        arm_gripper_board=1,
    )
    arm = build_arm(cfg)
    assert arm is not None
    assert arm.num_joints == 6
    assert arm.gripper_board == 1  # the configured board owns the end-effector


def test_build_arm_gate_defaults_when_no_limits_configured() -> None:
    gate = build_arm_gate(Config(), 3)
    assert gate.num_joints == 3
    assert gate.limit(0).max_dps == 90.0  # permissive default


def test_build_arm_gate_uses_configured_limits() -> None:
    cfg = Config(arm_joint_limits=[[-90.0, 90.0, 60.0], [-45.0, 45.0, 30.0]])
    gate = build_arm_gate(cfg, 2)
    assert gate.limit(1).min_deg == -45.0
    assert gate.limit(1).max_dps == 30.0


def test_build_arm_gate_length_mismatch_raises() -> None:
    cfg = Config(arm_joint_limits=[[-90.0, 90.0, 60.0]])  # 1 triple for a 3-joint arm
    with pytest.raises(UsageError):
        build_arm_gate(cfg, 3)


# ---- M-ARM-1 task 1.2: WS /arm/control through the host safety gate -------


async def _await_telemetry(c: TestClient) -> None:
    """Block until the drain has filled the position cache (move needs current angles)."""
    for _ in range(40):
        d = await (await c.get("/arm/telemetry")).json()
        if d["positions"]:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("arm telemetry never populated")


def test_arm_control_jog_acked_and_routed_to_manager() -> None:
    async def body() -> None:
        fake = RecordingArmTransport([0.0, 0.0, 0.0])
        arm = ArmManager([fake], linear_joint_map([3]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/arm/control")
            await ws.send_json({"cmd": "jvel", "joint": 0, "dps": 25.0})
            reply = await ws.receive_json()
            assert reply["type"] == "ack"
            await ws.close()
        # The jog reached the manager as a jvel frame for the right joint.
        assert "jvel" in fake.names()

    _run(body())


def test_arm_control_jpos_rejected_until_homed() -> None:
    async def body() -> None:
        fake = RecordingArmTransport([0.0])
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/arm/control")
            # Absolute move before homing -> nak from the host gate (never reaches the board).
            await ws.send_json({"cmd": "jpos", "joint": 0, "deg": 30.0})
            nak = await ws.receive_json()
            assert nak["type"] == "nak"
            assert "homed" in nak["reason"]
            assert "jpos" not in fake.names()

            # Home it, then the same move is accepted.
            await ws.send_json({"cmd": "home", "joint": 0})
            assert (await ws.receive_json())["type"] == "ack"
            await ws.send_json({"cmd": "jpos", "joint": 0, "deg": 30.0})
            assert (await ws.receive_json())["type"] == "ack"
            assert "jpos" in fake.names()
            await ws.close()

    _run(body())


def test_arm_control_estop_latches_until_cleared() -> None:
    async def body() -> None:
        fake = RecordingArmTransport([0.0])
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/arm/control")
            await ws.send_json({"cmd": "estop"})
            assert (await ws.receive_json())["type"] == "ack"
            assert "estop" in fake.names()

            # Motion is refused while latched.
            await ws.send_json({"cmd": "jvel", "joint": 0, "dps": 10.0})
            nak = await ws.receive_json()
            assert nak["type"] == "nak"
            assert "estop" in nak["reason"]

            # Clear, then motion is accepted again.
            await ws.send_json({"cmd": "clear_estop"})
            assert (await ws.receive_json())["type"] == "ack"
            await ws.send_json({"cmd": "jvel", "joint": 0, "dps": 10.0})
            assert (await ws.receive_json())["type"] == "ack"
            await ws.close()

    _run(body())


def test_arm_control_estop_latch_is_shared_across_connections() -> None:
    """The latch lives on AgentState, not per-socket — a second client must see it latched."""

    async def body() -> None:
        fake = RecordingArmTransport([0.0])
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            ws1 = await c.ws_connect("/arm/control")
            await ws1.send_json({"cmd": "estop"})
            assert (await ws1.receive_json())["type"] == "ack"
            await ws1.close()

            # A freshly-connected client inherits the latched state.
            ws2 = await c.ws_connect("/arm/control")
            await ws2.send_json({"cmd": "jvel", "joint": 0, "dps": 5.0})
            nak = await ws2.receive_json()
            assert nak["type"] == "nak"
            assert "estop" in nak["reason"]
            await ws2.close()

    _run(body())


def test_arm_control_move_synchronized_through_gate() -> None:
    async def body() -> None:
        fake = RecordingArmTransport([10.0, 20.0, 30.0])
        arm = ArmManager([fake], linear_joint_map([3]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            await _await_telemetry(c)
            ws = await c.ws_connect("/arm/control")
            for j in (0, 1):
                await ws.send_json({"cmd": "home", "joint": j})
                assert (await ws.receive_json())["type"] == "ack"
            await ws.send_json({"cmd": "move", "targets": {"0": 15.0, "1": 25.0}, "seconds": 1.0})
            assert (await ws.receive_json())["type"] == "ack"
            await ws.close()
        # move_synchronized fans out to a jmove per joint.
        assert fake.names().count("jmove") == 2

    _run(body())


def test_arm_control_move_naks_without_telemetry() -> None:
    async def body() -> None:
        fake = RecordingArmTransport([0.0])  # recv replays, but we home+move before draining
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/arm/control")
            await ws.send_json({"cmd": "home", "joint": 0})
            assert (await ws.receive_json())["type"] == "ack"
            # If the cache has no sample for the joint yet, move naks cleanly (no crash).
            from agent.app import STATE

            app[STATE].arm_positions = {}
            await ws.send_json({"cmd": "move", "targets": {"0": 5.0}, "seconds": 1.0})
            nak = await ws.receive_json()
            assert nak["type"] == "nak"
            assert "telemetry" in nak["reason"]
            await ws.close()

    _run(body())


def test_arm_telemetry_reports_homed_and_estop_state() -> None:
    async def body() -> None:
        fake = RecordingArmTransport([0.0, 0.0])
        arm = ArmManager([fake], linear_joint_map([2]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            d = await (await c.get("/arm/telemetry")).json()
            assert d["homed"] == {"0": False, "1": False}
            assert d["estopped"] is False

            ws = await c.ws_connect("/arm/control")
            await ws.send_json({"cmd": "home", "joint": 1})
            assert (await ws.receive_json())["type"] == "ack"
            await ws.send_json({"cmd": "estop"})
            assert (await ws.receive_json())["type"] == "ack"
            await ws.close()

            d = await (await c.get("/arm/telemetry")).json()
            assert d["homed"] == {"0": False, "1": True}
            assert d["estopped"] is True

    _run(body())


def test_arm_control_clean_error_when_no_arm() -> None:
    async def body() -> None:
        app = build_app(transport=ResponderTransport(), trust_loopback=True)  # no arm
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/arm/control")
            await ws.send_json({"cmd": "jvel", "joint": 0, "dps": 10.0})
            nak = await ws.receive_json()
            assert nak["type"] == "nak"
            assert "no arm" in nak["reason"]
            await ws.close()

    _run(body())


def test_arm_control_bad_frame_naks_without_crashing() -> None:
    async def body() -> None:
        fake = RecordingArmTransport([0.0])
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/arm/control")
            await ws.send_json({"cmd": "wat"})  # unknown command
            assert (await ws.receive_json())["type"] == "nak"
            await ws.send_json({"cmd": "jvel", "joint": 0})  # missing dps
            assert (await ws.receive_json())["type"] == "nak"
            # The socket is still alive and serving after bad frames.
            await ws.send_json({"cmd": "jstop", "joint": 0})
            assert (await ws.receive_json())["type"] == "ack"
            await ws.close()

    _run(body())


# ---- M-ARM-2 task 2.4: gripper / tool through the control surface -----------


def test_arm_control_grip_and_tool_through_gate() -> None:
    async def body() -> None:
        fake = RecordingArmTransport([0.0])
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            ws = await c.ws_connect("/arm/control")
            await ws.send_json({"cmd": "grip", "deg": 40.0})
            assert (await ws.receive_json())["type"] == "ack"
            await ws.send_json({"cmd": "tool", "on": True})
            assert (await ws.receive_json())["type"] == "ack"

            # Both are refused while e-stop is latched.
            await ws.send_json({"cmd": "estop"})
            assert (await ws.receive_json())["type"] == "ack"
            await ws.send_json({"cmd": "grip", "deg": 10.0})
            grip_nak = await ws.receive_json()
            assert grip_nak["type"] == "nak" and "estop" in grip_nak["reason"]
            await ws.send_json({"cmd": "tool", "on": False})
            assert (await ws.receive_json())["type"] == "nak"
            await ws.close()
        names = fake.names()
        assert "grip" in names and "tool" in names

    _run(body())


def test_arm_telemetry_includes_gripper_state() -> None:
    async def body() -> None:
        fake = GripperArmTransport([10.0], grip_deg=55.0, tool=1.0)
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            gripper = None
            for _ in range(40):
                d = await (await c.get("/arm/telemetry")).json()
                if d.get("gripper"):
                    gripper = d["gripper"]
                    break
                await asyncio.sleep(0.02)
            assert gripper == {"deg": 55.0, "tool": True}

    _run(body())


# ---- M-ARM-3 task 3.4: forward-kinematics pose in /arm/telemetry ------------


def test_arm_telemetry_pose_present_with_model() -> None:
    pytest.importorskip("ikpy")  # needs the optional [arm-ik] extra

    async def body() -> None:
        fake = FakeArmTransport([10.0, 20.0, 30.0, 0.0, 0.0, 0.0])
        arm = ArmManager([fake], linear_joint_map([6]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            pose = None
            for _ in range(40):
                d = await (await c.get("/arm/telemetry")).json()
                if d["pose"] is not None:
                    pose = d["pose"]
                    break
                await asyncio.sleep(0.02)
            assert pose is not None, "FK pose never appeared"
            assert set(pose) == {"x", "y", "z", "rx", "ry", "rz"}
            assert all(isinstance(v, (int, float)) for v in pose.values())

    _run(body())


def test_arm_telemetry_pose_absent_without_the_extra() -> None:
    """When the FK model/ikpy isn't available the pose is cleanly absent — never a crash."""

    async def body() -> None:
        fake = FakeArmTransport([10.0, 20.0, 30.0])
        arm = ArmManager([fake], linear_joint_map([3]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            # Simulate "no [arm-ik] extra": the build was tried and produced no chain.
            from agent.app import STATE

            app[STATE].arm_fk = None
            app[STATE].arm_fk_tried = True
            d = await (await c.get("/arm/telemetry")).json()
            assert d["enabled"] is True
            assert d["pose"] is None

    _run(body())


# ---- M-ARM-4 task 4.4: Cartesian move (IK) through the control surface ------


async def _home_all(ws: Any, n: int) -> None:
    for j in range(n):
        await ws.send_json({"cmd": "home", "joint": j})
        assert (await ws.receive_json())["type"] == "ack"


def test_arm_control_move_cartesian_solves_and_routes_to_manager() -> None:
    """A reachable Cartesian pose is IK-solved, passes the same homing/telemetry gate as a joint
    `move`, and fans out to per-joint jmoves on the board."""
    pytest.importorskip("ikpy")  # needs the optional [arm-ik] extra (real IK)
    from pibot.arm.kinematics import ForwardKinematics

    async def body() -> None:
        fake = RecordingArmTransport([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])  # 6-joint arm at zero
        arm = ArmManager([fake], linear_joint_map([6]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        target = ForwardKinematics().solve({1: 20.0, 2: -15.0})  # a known-reachable EE pose
        async with TestClient(TestServer(app)) as c:
            await _await_telemetry(c)
            ws = await c.ws_connect("/arm/control")
            await _home_all(ws, 6)  # IK targets all joints → gate.move needs every joint homed
            await ws.send_json(
                {
                    "cmd": "move_cartesian",
                    "x": target.x,
                    "y": target.y,
                    "z": target.z,
                    "rx": target.rx,
                    "ry": target.ry,
                    "rz": target.rz,
                    "seconds": 1.0,
                }
            )
            assert (await ws.receive_json())["type"] == "ack"
            await ws.close()
        assert "jmove" in fake.names()  # the synchronized move reached the board

    _run(body())


def test_arm_control_move_cartesian_naks_unreachable_pose() -> None:
    """A pose far outside the workspace is rejected by IK and naks 'unreachable' (NOT 'bad frame'),
    and never reaches the board — IKError must not be swallowed by the parse-error handler."""
    pytest.importorskip("ikpy")

    async def body() -> None:
        fake = RecordingArmTransport([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        arm = ArmManager([fake], linear_joint_map([6]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            await _await_telemetry(c)
            ws = await c.ws_connect("/arm/control")
            await _home_all(ws, 6)
            await ws.send_json(
                {"cmd": "move_cartesian", "x": 10.0, "y": 0.0, "z": 0.0, "seconds": 1.0}
            )
            nak = await ws.receive_json()
            assert nak["type"] == "nak"
            assert "unreachable" in nak["reason"]
            assert "jmove" not in fake.names()
            await ws.close()

    _run(body())


def test_arm_control_move_cartesian_clean_error_without_ik() -> None:
    """When the [arm-ik] extra/model isn't available the Cartesian move naks cleanly. arm-ik IS
    installed in the gate, so the absent path is forced by pre-disabling the IK cache."""

    async def body() -> None:
        fake = RecordingArmTransport([0.0])
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            from agent.app import STATE

            app[STATE].arm_ik = None  # simulate "no [arm-ik] extra": build tried, produced nothing
            app[STATE].arm_ik_tried = True
            ws = await c.ws_connect("/arm/control")
            await ws.send_json(
                {"cmd": "move_cartesian", "x": 0.3, "y": 0.0, "z": 0.4, "seconds": 1.0}
            )
            nak = await ws.receive_json()
            assert nak["type"] == "nak"
            assert "IK unavailable" in nak["reason"]
            assert "jmove" not in fake.names()
            await ws.close()

    _run(body())


# ---- M-ARM-1 task 1.3: AgentClient motion methods hit the right frames -----


def test_agent_client_arm_methods_route_through_the_gate() -> None:
    async def body() -> None:
        from pibot.control.client import AgentClient

        fake = RecordingArmTransport([10.0, 20.0])
        arm = ArmManager([fake], linear_joint_map([2]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        async with TestClient(TestServer(app)) as c:
            await _await_telemetry(c)
            client = AgentClient(str(c.make_url("")).rstrip("/"))
            await client.open()
            try:
                assert (await client.arm_jog(0, 15.0))["type"] == "ack"
                # Absolute move before homing is refused by the host gate.
                assert (await client.arm_move_joint(0, 30.0))["type"] == "nak"
                assert (await client.arm_home(0))["type"] == "ack"
                assert (await client.arm_home(1))["type"] == "ack"
                assert (await client.arm_move_joint(0, 30.0))["type"] == "ack"  # -> jpos
                assert (await client.arm_move_joint(1, 10.0, speed=5.0))["type"] == "ack"  # jmove
                assert (await client.arm_move_joints({0: 12.0, 1: 22.0}, 1.0))["type"] == "ack"
                assert (await client.arm_grip(35.0))["type"] == "ack"
                assert (await client.arm_tool(True))["type"] == "ack"
                assert (await client.arm_estop())["type"] == "ack"
                assert (await client.arm_jog(0, 5.0))["type"] == "nak"  # latched
                assert (await client.arm_grip(10.0))["type"] == "nak"  # gripper latched too
                assert (await client.arm_clear_estop())["type"] == "ack"
                assert (await client.arm_enable(False))["type"] == "ack"
            finally:
                await client.close()
        names = fake.names()
        for verb in ("jvel", "jpos", "jmove", "home", "estop", "enable", "grip", "tool"):
            assert verb in names, f"{verb} never reached the board"

    _run(body())


def test_agent_client_arm_move_cartesian_routes_through_ik() -> None:
    """AgentClient.arm_move_cartesian drives a reachable pose to the board (ack) and surfaces an
    unreachable one as a nak — exercising the client frame end-to-end through real IK."""
    pytest.importorskip("ikpy")
    from pibot.arm.kinematics import ForwardKinematics

    async def body() -> None:
        from pibot.control.client import AgentClient

        fake = RecordingArmTransport([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        arm = ArmManager([fake], linear_joint_map([6]))
        app = build_app(transport=ResponderTransport(), trust_loopback=True, arm=arm)
        target = ForwardKinematics().solve({1: 15.0, 2: -20.0})
        async with TestClient(TestServer(app)) as c:
            await _await_telemetry(c)
            client = AgentClient(str(c.make_url("")).rstrip("/"))
            await client.open()
            try:
                for j in range(6):
                    assert (await client.arm_home(j))["type"] == "ack"
                ack = await client.arm_move_cartesian(
                    target.x, target.y, target.z, 1.0, rx=target.rx, ry=target.ry, rz=target.rz
                )
                assert ack["type"] == "ack"
                nak = await client.arm_move_cartesian(10.0, 0.0, 0.0, 1.0)
                assert nak["type"] == "nak" and "unreachable" in nak["reason"]
            finally:
                await client.close()
        assert "jmove" in fake.names()

    _run(body())


# ---- M-ARM-5 task 5.4: pose/program persistence + runner -------------------


def test_arm_pose_crud_records_from_telemetry_and_survives_restart(tmp_path: Any) -> None:
    async def body() -> None:
        fake = FakeArmTransport([12.5, -4.0])
        arm = ArmManager([fake], linear_joint_map([2]))
        app = build_app(
            transport=ResponderTransport(),
            trust_loopback=True,
            arm=arm,
            arm_state_dir=tmp_path,
        )
        async with TestClient(TestServer(app)) as c:
            await _await_telemetry(c)
            created = await c.post("/arm/poses", json={"name": "ready"})
            assert created.status == 201
            pose = await created.json()
            assert pose["name"] == "ready"
            assert pose["joints"] == {"0": 12.5, "1": -4.0}

            listed = await (await c.get("/arm/poses")).json()
            assert [row["name"] for row in listed["poses"]] == ["ready"]

        # Restart against the same state dir: the recorded pose is still there.
        app2 = build_app(
            transport=ResponderTransport(),
            trust_loopback=True,
            arm_state_dir=tmp_path,
        )
        async with TestClient(TestServer(app2)) as c:
            fetched = await (await c.get("/arm/poses/ready")).json()
            assert fetched["name"] == "ready"
            assert fetched["joints"] == {"0": 12.5, "1": -4.0}
            deleted = await c.delete("/arm/poses/ready")
            assert deleted.status == 200
            assert (await c.get("/arm/poses/ready")).status == 404

    _run(body())


def test_arm_program_crud_runs_steps_in_order_and_persists(tmp_path: Any) -> None:
    async def body() -> None:
        from agent.app import STATE

        fake = RecordingArmTransport([0.0, 0.0])
        arm = ArmManager([fake], linear_joint_map([2]))
        app = build_app(
            transport=ResponderTransport(),
            trust_loopback=True,
            arm=arm,
            arm_state_dir=tmp_path,
        )
        app[STATE].arm_positions = {0: 0.0, 1: 0.0}
        app[STATE].arm_positions_ts = time.time()
        app[STATE].arm_homed = {0, 1}
        async with TestClient(TestServer(app)) as c:
            pose_resp = await c.post(
                "/arm/poses",
                json={
                    "pose": {
                        "name": "ready",
                        "joints": {"0": 20.0, "1": -10.0},
                        "created": 1.0,
                    }
                },
            )
            assert pose_resp.status == 201

            program_body = {
                "name": "demo",
                "created": 2.0,
                "steps": [
                    {"kind": "moveJ", "pose": "ready", "seconds": 0.05},
                    {"kind": "wait", "seconds": 0.02},
                    {"kind": "grip", "deg": 15.0},
                    {"kind": "tool", "on": True},
                ],
            }
            created = await c.post("/arm/programs", json=program_body)
            assert created.status == 201

            listed = await (await c.get("/arm/programs")).json()
            assert [row["name"] for row in listed["programs"]] == ["demo"]

            run = await c.post("/arm/programs/demo/run")
            assert run.status == 202
            for _ in range(40):
                task = app[STATE].arm_program_task
                if task is None or task.done():
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("program task never finished")

        names = fake.names()
        assert "jmove" in names
        assert names.index("grip") > names.index("jmove")
        assert names.index("tool") > names.index("grip")

        app2 = build_app(
            transport=ResponderTransport(),
            trust_loopback=True,
            arm_state_dir=tmp_path,
        )
        async with TestClient(TestServer(app2)) as c:
            fetched = await (await c.get("/arm/programs/demo")).json()
            assert fetched["name"] == "demo"
            assert fetched["steps"][0]["kind"] == "moveJ"

    _run(body())


def test_arm_program_stop_aborts_mid_run(tmp_path: Any) -> None:
    async def body() -> None:
        from agent.app import STATE

        fake = RecordingArmTransport([0.0])
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(
            transport=ResponderTransport(),
            trust_loopback=True,
            arm=arm,
            arm_state_dir=tmp_path,
        )
        app[STATE].arm_positions = {0: 0.0}
        app[STATE].arm_positions_ts = time.time()
        app[STATE].arm_homed = {0}
        async with TestClient(TestServer(app)) as c:
            await c.post(
                "/arm/programs",
                json={
                    "name": "linger",
                    "steps": [
                        {"kind": "wait", "seconds": 0.5},
                        {"kind": "grip", "deg": 5.0},
                    ],
                },
            )
            assert (await c.post("/arm/programs/linger/run")).status == 202
            await asyncio.sleep(0.05)
            stopped = await c.post("/arm/programs/stop")
            assert stopped.status == 200
            for _ in range(40):
                task = app[STATE].arm_program_task
                if task is None or task.done():
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("program stop did not abort the task")

        assert "grip" not in fake.names()

    _run(body())


def test_arm_program_status_progress_and_stop_surface_in_telemetry(tmp_path: Any) -> None:
    async def body() -> None:
        from agent.app import STATE

        fake = RecordingArmTransport([0.0])
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(
            transport=ResponderTransport(),
            trust_loopback=True,
            arm=arm,
            arm_state_dir=tmp_path,
        )
        app[STATE].arm_positions = {0: 0.0}
        app[STATE].arm_positions_ts = time.time()
        app[STATE].arm_homed = {0}
        async with TestClient(TestServer(app)) as c:
            await c.post(
                "/arm/programs",
                json={
                    "name": "linger",
                    "steps": [
                        {"kind": "wait", "seconds": 0.5},
                        {"kind": "grip", "deg": 5.0},
                    ],
                },
            )
            assert (await c.post("/arm/programs/linger/run")).status == 202

            # While the wait step runs, the control plane must remain responsive and telemetry must
            # expose progress so the UI can show live step state.
            for _ in range(40):
                telemetry = await (await c.get("/arm/telemetry")).json()
                program = telemetry.get("program")
                if program and program["state"] == "running":
                    assert program["name"] == "linger"
                    assert program["current_step"] == 1
                    assert program["total_steps"] == 2
                    assert program["current_kind"] == "wait"
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("telemetry never reported a running program")

            assert (await c.get("/health")).status == 200

            assert (await c.post("/arm/programs/stop")).status == 200
            for _ in range(40):
                telemetry = await (await c.get("/arm/telemetry")).json()
                program = telemetry.get("program")
                if program and program["state"] == "stopped":
                    assert program["name"] == "linger"
                    assert program["message"] == "stopped"
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("telemetry never reported the stopped program")

    _run(body())


def test_arm_estop_aborts_running_program(tmp_path: Any) -> None:
    async def body() -> None:
        from agent.app import STATE

        fake = RecordingArmTransport([0.0])
        arm = ArmManager([fake], linear_joint_map([1]))
        app = build_app(
            transport=ResponderTransport(),
            trust_loopback=True,
            arm=arm,
            arm_state_dir=tmp_path,
        )
        app[STATE].arm_positions = {0: 0.0}
        app[STATE].arm_positions_ts = time.time()
        app[STATE].arm_homed = {0}
        async with TestClient(TestServer(app)) as c:
            await c.post(
                "/arm/programs",
                json={
                    "name": "abort-me",
                    "steps": [
                        {"kind": "wait", "seconds": 0.5},
                        {"kind": "grip", "deg": 5.0},
                    ],
                },
            )
            assert (await c.post("/arm/programs/abort-me/run")).status == 202
            await asyncio.sleep(0.05)
            ws = await c.ws_connect("/arm/control")
            await ws.send_json({"cmd": "estop"})
            assert (await ws.receive_json())["type"] == "ack"
            await ws.close()
            for _ in range(40):
                task = app[STATE].arm_program_task
                if task is None or task.done():
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("e-stop did not abort the task")

        assert "grip" not in fake.names()
        assert app[STATE].arm_estopped is True

    _run(body())
