"""M5 E2E — drive the robot over a *wireless* (BLE) transport, full stack, in-process.

The whole control path runs for real: the WebSocket :class:`AgentClient` -> the aiohttp
agent -> the safety subsystem -> :class:`BleTransport` (its own event-loop thread + queue
bridge) -> a firmware-mirror peripheral. The only stand-in is the radio itself (a fake
bleak client), exactly as a sandbox stands in for an external service.

Two acceptance behaviours:
  1. Operator goes quiet while the link is up -> the deadman stops the robot *over BLE*.
  2. The radio link drops -> the agent observes the transport as down (``open`` False), at
     which point the firmware's independent watchdog is the backstop.
"""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestServer

from agent.app import build_app
from pibot.control.client import AgentClient
from pibot.control.echo import EchoResponder
from pibot.control.teleop import apply_action, key_to_action
from pibot.protocol.codec import decode
from pibot.transport.ble import NUS_RX, BleTransport


def _run(coro) -> None:
    asyncio.run(coro)


def _vcgencmd(args: list[str]) -> str:
    return {
        ("measure_temp",): "temp=48.0'C",
        ("get_throttled",): "throttled=0x0",
        ("measure_volts", "core"): "volt=0.88V",
    }[tuple(args)]


class RobotBleClient:
    """A fake BLE peripheral that behaves like the robot firmware: ACK/telemetry on write."""

    def __init__(self, address: str, disconnected_callback=None) -> None:
        self.address = address
        self._cb = disconnected_callback
        self._notify = None
        self.is_connected = False
        self._responder = EchoResponder("ascii")
        self.sent: list[bytes] = []  # command frames the host wrote to us

    async def connect(self) -> bool:
        self.is_connected = True
        return True

    async def start_notify(self, uuid, callback) -> None:
        self._notify = callback

    async def write_gatt_char(self, uuid, data, response: bool = False) -> None:
        if not self.is_connected:
            raise RuntimeError("ble link down")
        assert uuid == NUS_RX
        frame = bytes(data)
        self.sent.append(frame)
        for out in self._responder.feed(frame):  # robot answers with ACK + telemetry
            if self._notify is not None:
                self._notify(uuid, bytearray(out))

    async def disconnect(self) -> None:
        self.is_connected = False

    def drop_radio(self) -> None:
        """The BLE link is lost: bleak fires the disconnected callback."""
        self.is_connected = False
        if self._cb is not None:
            self._cb(self)


def _ble_app(holder: dict, **kw):
    def factory(address, disconnected_callback=None):
        client = RobotBleClient(address, disconnected_callback)
        holder["robot"] = client
        return client

    transport = BleTransport("AA:BB:CC:DD:EE:FF", client_factory=factory)
    return build_app(transport=transport, vcgencmd_run=_vcgencmd, max_rate_hz=0, **kw)


def test_wireless_drive_then_quiet_triggers_stop_over_ble() -> None:
    async def body() -> None:
        holder: dict = {}
        server = TestServer(_ble_app(holder, deadman_ms=80))
        await server.start_server()
        try:
            base = str(server.make_url("")).rstrip("/")
            client = AgentClient(base)
            await client.connect()

            reply = await apply_action(client, key_to_action("w"))  # drive forward over BLE
            assert reply is not None and reply["ack"] is True

            await asyncio.sleep(0.4)  # operator goes quiet, past the deadman window
            await client.close()

            robot = holder["robot"]
            stops = [f for f in robot.sent if decode(f, "ascii").name == "stop"]
            assert stops, "deadman did not stop the robot over the wireless link"
        finally:
            await server.close()

    _run(body())


def test_wireless_radio_drop_marks_transport_down() -> None:
    async def body() -> None:
        holder: dict = {}
        server = TestServer(_ble_app(holder, deadman_ms=5000))  # long deadman: isolate the drop
        await server.start_server()
        try:
            base = str(server.make_url("")).rstrip("/")
            client = AgentClient(base)
            await client.connect()

            await apply_action(client, key_to_action("w"))
            snap = await client.telemetry()
            assert snap["transport"]["open"] is True  # link healthy while driving

            holder["robot"].drop_radio()  # the BLE radio drops

            # the agent observes the wireless link as down (firmware watchdog then backstops)
            down = False
            for _ in range(50):
                snap = await client.telemetry()
                if snap["transport"]["open"] is False:
                    down = True
                    break
                await asyncio.sleep(0.02)
            assert down, "agent did not observe the dropped wireless transport"
            await client.close()
        finally:
            await server.close()

    _run(body())
