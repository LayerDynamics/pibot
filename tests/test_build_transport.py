"""T5.3-5.5 wiring — build_transport selects every M5 backend from config."""

from __future__ import annotations

import pytest

from agent.pibotd import build_transport
from pibot.config import Config
from pibot.errors import UsageError


def test_build_rfcomm() -> None:
    t = build_transport(Config(transport="rfcomm", rfcomm_address="AA:BB:CC:DD:EE:FF"))
    info = t.info
    assert info["backend"] == "rfcomm"
    assert info["address"] == "AA:BB:CC:DD:EE:FF"


def test_build_uart_selects_serial0() -> None:
    t = build_transport(Config(transport="uart"))
    assert t.info["backend"] == "serial"
    assert t.info["port"] == "/dev/serial0"


def test_build_ble() -> None:
    t = build_transport(Config(transport="ble", ble_address="AA:BB:CC:DD:EE:FF"))
    assert t.info["backend"] == "ble"
    assert t.info["address"] == "AA:BB:CC:DD:EE:FF"


def test_build_i2c() -> None:
    t = build_transport(Config(transport="i2c", i2c_bus=1, i2c_address=0x08))
    info = t.info
    assert info["backend"] == "i2c"
    assert info["bus"] == 1
    assert info["address"] == 0x08


def test_build_unknown_transport_raises() -> None:
    with pytest.raises(UsageError):
        build_transport(Config(transport="smoke-signals"))
