"""T5.4 — BleTransport over a fake bleak client: notify->recv, write->send, drop fail-safe.

BLE is async (bleak); the Transport contract is sync. The backend runs a private event
loop in a daemon thread and bridges open/send/close across it, while notifications land
in a thread-safe queue that ``recv`` drains. The fake client echoes writes back through
the notify characteristic so the standard loopback contract applies.
"""

from __future__ import annotations

from helpers import assert_transport_contract

from pibot.transport.ble import NUS_RX, NUS_TX, BleTransport


class FakeBleakClient:
    """A loopback Nordic-UART peripheral: writes to RX echo back on the TX notify char."""

    def __init__(self, address: str, disconnected_callback=None) -> None:
        self.address = address
        self._disconnected_callback = disconnected_callback
        self._notify_cb = None
        self.is_connected = False
        self.writes: list[bytes] = []
        self._split_next = False

    async def connect(self) -> bool:
        self.is_connected = True
        return True

    async def start_notify(self, uuid, callback) -> None:
        assert uuid == NUS_TX
        self._notify_cb = callback

    async def write_gatt_char(self, uuid, data, response: bool = False) -> None:
        assert uuid == NUS_RX
        if not self.is_connected:
            raise RuntimeError("not connected")
        self.writes.append(bytes(data))
        # echo back through the notify characteristic (loopback peripheral)
        if self._notify_cb is not None:
            if self._split_next:  # deliver in two chunks to exercise reassembly
                mid = max(1, len(data) // 2)
                self._notify_cb(uuid, bytearray(data[:mid]))
                self._notify_cb(uuid, bytearray(data[mid:]))
            else:
                self._notify_cb(uuid, bytearray(data))

    async def disconnect(self) -> None:
        self.is_connected = False

    def simulate_drop(self) -> None:
        """Mimic the radio link dropping: bleak fires the disconnected callback."""
        self.is_connected = False
        if self._disconnected_callback is not None:
            self._disconnected_callback(self)


def _factory(holder: dict):
    def make(address, disconnected_callback=None):
        client = FakeBleakClient(address, disconnected_callback)
        holder["client"] = client
        return client

    return make


def _make() -> BleTransport:
    return BleTransport("AA:BB:CC:DD:EE:FF", client_factory=_factory({}))


def test_ble_satisfies_transport_contract() -> None:
    assert_transport_contract(_make)


def test_info_reports_ble_backend() -> None:
    t = _make()
    t.open()
    info = t.info
    assert info["backend"] == "ble"
    assert info["address"] == "AA:BB:CC:DD:EE:FF"
    t.close()


def test_send_writes_to_rx_characteristic() -> None:
    holder: dict = {}
    t = BleTransport("AA:BB:CC:DD:EE:FF", client_factory=_factory(holder))
    t.open()
    t.send(b">1,ping*5B\n")
    assert holder["client"].writes == [b">1,ping*5B\n"]
    t.close()


def test_partial_notifications_reassemble() -> None:
    holder: dict = {}
    t = BleTransport("AA:BB:CC:DD:EE:FF", client_factory=_factory(holder))
    t.open()
    holder["client"]._split_next = True  # frame arrives as two notifications
    t.send(b">1,ping*5B\n")
    assert t.recv(0.5) == b">1,ping*5B\n"
    t.close()


def test_disconnect_fails_safe() -> None:
    holder: dict = {}
    t = BleTransport("AA:BB:CC:DD:EE:FF", client_factory=_factory(holder))
    t.open()
    assert t.is_open is True
    holder["client"].simulate_drop()  # radio link lost
    assert t.recv(0.05) is None  # no data, not connected -> fail safe (deadman stops robot)
    assert t.is_open is False
    t.close()
