"""T5.5 — I2CTransport over a fake smbus2 bus: 32-byte block framing, drop-on-bus-error."""

from __future__ import annotations

from helpers import assert_transport_contract

from pibot.transport.i2c import I2CTransport


class FakeBus:
    """A loopback I2C slave: block writes append to a buffer that block reads drain.

    Models the SMBus 32-byte block cap and zero-padding (a real slave returns its
    buffer padded out to the requested length).
    """

    def __init__(self) -> None:
        self.tx = bytearray()
        self.writes: list[list[int]] = []
        self.fail = False

    def write_i2c_block_data(self, addr: int, reg: int, data: list[int]) -> None:
        if self.fail:
            raise OSError("i2c bus write error")
        assert len(data) <= 32  # SMBus block cap
        self.writes.append(list(data))
        self.tx.extend(bytes(data))  # loopback to the read side

    def read_i2c_block_data(self, addr: int, reg: int, length: int) -> list[int]:
        if self.fail:
            raise OSError("i2c bus read error")
        chunk = self.tx[:length]
        del self.tx[:length]
        out = list(chunk)
        out += [0] * (length - len(out))  # slave pads short reads with 0x00
        return out

    def close(self) -> None:
        pass


def _make() -> I2CTransport:
    return I2CTransport(bus=1, address=0x08, bus_factory=FakeBus)


def test_i2c_satisfies_transport_contract() -> None:
    assert_transport_contract(_make)


def test_info_reports_i2c_backend() -> None:
    t = _make()
    t.open()
    info = t.info
    assert info["backend"] == "i2c"
    assert info["address"] == 0x08
    assert info["bus"] == 1
    t.close()


def test_long_frame_chunked_into_32_byte_blocks_and_reassembled() -> None:
    bus = FakeBus()
    t = I2CTransport(bus=1, address=0x08, bus_factory=lambda: bus)
    t.open()
    frame = b">1,drive v=0.5 w=0.0 padding=" + b"x" * 60 + b"*AA\n"  # > 32 bytes
    assert len(frame) > 32
    t.send(frame)
    assert len(bus.writes) >= 2  # split across multiple block writes
    assert all(len(w) <= 32 for w in bus.writes)
    got = t.recv(0.5)
    assert got == frame  # reassembled whole despite chunking
    t.close()


def test_bus_write_error_fails_safe() -> None:
    bus = FakeBus()
    t = I2CTransport(bus=1, address=0x08, bus_factory=lambda: bus)
    t.open()
    bus.fail = True
    import pytest

    from pibot.transport.base import TransportError

    with pytest.raises(TransportError):
        t.send(b">1,ping*5B\n")
    assert t.is_open is False  # bus error drops the link -> deadman stops the robot


def test_bus_read_error_returns_none_and_drops() -> None:
    bus = FakeBus()
    t = I2CTransport(bus=1, address=0x08, bus_factory=lambda: bus)
    t.open()
    bus.fail = True
    assert t.recv(0.05) is None
    assert t.is_open is False
