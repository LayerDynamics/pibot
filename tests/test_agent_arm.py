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
    )
    arm = build_arm(cfg)
    assert arm is not None
    assert arm.num_joints == 6


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
                assert (await client.arm_estop())["type"] == "ack"
                assert (await client.arm_jog(0, 5.0))["type"] == "nak"  # latched
                assert (await client.arm_clear_estop())["type"] == "ack"
                assert (await client.arm_enable(False))["type"] == "ack"
            finally:
                await client.close()
        names = fake.names()
        for verb in ("jvel", "jpos", "jmove", "home", "estop", "enable"):
            assert verb in names, f"{verb} never reached the board"

    _run(body())
