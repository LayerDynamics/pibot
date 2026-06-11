"""T5.3 — RfcommTransport: Bluetooth-Classic as a serial device (/dev/rfcomm*) + bind."""

from __future__ import annotations

from helpers import assert_transport_contract

from pibot.transport.rfcomm import RfcommTransport, bind_command, release_command


def _make() -> RfcommTransport:
    # RFCOMM is a serial device; reuse pyserial's loopback to exercise the real path.
    return RfcommTransport(port="loop://")


def test_rfcomm_satisfies_transport_contract() -> None:
    assert_transport_contract(_make)


def test_info_reports_rfcomm_backend() -> None:
    t = RfcommTransport(port="loop://", address="AA:BB:CC:DD:EE:FF", channel=1)
    t.open()
    info = t.info
    assert info["backend"] == "rfcomm"
    assert info["address"] == "AA:BB:CC:DD:EE:FF"
    t.close()


def test_default_port_is_rfcomm0() -> None:
    t = RfcommTransport(address="AA:BB:CC:DD:EE:FF")
    assert t.info["port"] == "/dev/rfcomm0"


def test_bind_command_construction() -> None:
    assert bind_command("AA:BB:CC:DD:EE:FF") == ["rfcomm", "bind", "0", "AA:BB:CC:DD:EE:FF", "1"]
    assert bind_command("AA:BB:CC:DD:EE:FF", channel=3, dev=2) == [
        "rfcomm",
        "bind",
        "2",
        "AA:BB:CC:DD:EE:FF",
        "3",
    ]


def test_release_command_construction() -> None:
    assert release_command() == ["rfcomm", "release", "0"]
    assert release_command(dev=2) == ["rfcomm", "release", "2"]


def test_link_drop_fails_safe() -> None:
    """A dropped BT link makes the serial read raise -> transport drops, recv returns None."""

    class _Dropping:
        is_open = True

        def __init__(self) -> None:
            self.in_waiting = 0

        def read(self, _n: int) -> bytes:
            raise OSError("rfcomm device disconnected")

        def write(self, _b: bytes) -> None:  # pragma: no cover - not exercised here
            pass

        def close(self) -> None:
            self.is_open = False

    t = RfcommTransport(port="loop://", serial_factory=_Dropping)
    t.open()
    assert t.is_open is True
    assert t.recv(0.05) is None  # link dropped -> fail safe, no exception
    assert t.is_open is False
