"""T5.5 — GPIO-UART finalization: /dev/serial0 selection + setup documentation."""

from __future__ import annotations

from pibot.transport.serial import DEFAULT_UART_PORT, UART_SETUP_DOC, uart_transport


def test_uart_selects_serial0_by_default() -> None:
    assert DEFAULT_UART_PORT == "/dev/serial0"
    t = uart_transport(serial_factory=lambda: _StubSerial())
    assert t.info["port"] == "/dev/serial0"
    assert t.info["backend"] == "serial"


def test_uart_transport_honors_baud() -> None:
    t = uart_transport(baud=57600, serial_factory=lambda: _StubSerial())
    assert t.info["baud"] == 57600


def test_uart_setup_doc_states_enable_uart_and_level_shifter() -> None:
    doc = UART_SETUP_DOC.lower()
    assert "enable_uart=1" in UART_SETUP_DOC  # config requirement (case-sensitive token)
    assert "level shifter" in doc  # Pi 3.3 V <-> 5 V logic warning
    assert "3.3" in UART_SETUP_DOC and "5 v" in doc


class _StubSerial:
    is_open = True

    def __init__(self) -> None:
        self.in_waiting = 0

    def read(self, _n: int) -> bytes:
        return b""

    def write(self, _b: bytes) -> None:
        pass

    def close(self) -> None:
        self.is_open = False
