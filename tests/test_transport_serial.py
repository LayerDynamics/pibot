"""T3.3 — SerialTransport over pyserial's loopback URL (real serial API, no hardware)."""

from __future__ import annotations

import time

from helpers import assert_transport_contract

from pibot.transport.serial import SerialTransport


def _make() -> SerialTransport:
    return SerialTransport("loop://")


def test_serial_satisfies_contract() -> None:
    assert_transport_contract(_make)


def test_multiple_frames_in_order() -> None:
    t = SerialTransport("loop://")
    t.open()
    t.send(b">1,ping*5B\n")
    t.send(b">2,stop*1A\n")
    assert t.recv(0.5) == b">1,ping*5B\n"
    assert t.recv(0.5) == b">2,stop*1A\n"
    assert t.recv(0.02) is None
    t.close()


def test_partial_bytes_reassemble() -> None:
    t = SerialTransport("loop://")
    t.open()
    t._serial.write(b">1,pi")  # half a frame on the wire
    assert t.recv(0.05) is None
    t._serial.write(b"ng*5B\n")  # the rest
    assert t.recv(0.5) == b">1,ping*5B\n"
    t.close()


def test_timeout_returns_none() -> None:
    t = SerialTransport("loop://")
    t.open()
    start = time.monotonic()
    assert t.recv(0.1) is None
    assert time.monotonic() - start >= 0.09
    t.close()


def test_reconnect_after_close() -> None:
    t = SerialTransport("loop://")
    t.open()
    t.send(b">1,ping*5B\n")
    assert t.recv(0.5) == b">1,ping*5B\n"
    t.close()
    assert t.is_open is False
    t.open()
    assert t.is_open is True
    t.send(b">2,stop*1A\n")
    assert t.recv(0.5) == b">2,stop*1A\n"
    t.close()


def test_info_reports_backend_and_baud() -> None:
    t = SerialTransport("loop://", baud=57600)
    t.open()
    info = t.info
    assert info["backend"] == "serial"
    assert info["baud"] == 57600
    assert info["port"] == "loop://"
    t.close()
