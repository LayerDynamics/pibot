"""pibotd entrypoint — build the transport from config and serve the agent.

Run on the Pi as ``python -m agent``. Selects the robot transport from config
(``serial`` / ``tcp`` to the ESP32 / ``responder`` for no-hardware dev / ``loopback``),
builds the aiohttp app, and serves it on the configured bind address.
"""

from __future__ import annotations

from aiohttp import web

from agent import __version__
from agent.app import build_app
from agent.auth import load_token
from pibot.config import Config, load_config
from pibot.errors import UsageError
from pibot.transport.base import Transport


def build_transport(cfg: Config) -> Transport:
    """Construct the robot transport selected by ``cfg.transport``."""
    if cfg.transport == "tcp":
        from pibot.transport.tcp import TcpTransport

        return TcpTransport(cfg.robot_host, cfg.tcp_port)
    if cfg.transport == "serial":
        from pibot.transport.serial import SerialTransport

        return SerialTransport(cfg.serial_port, cfg.serial_baud)
    if cfg.transport == "uart":
        from pibot.transport.serial import uart_transport

        return uart_transport(cfg.serial_baud)
    if cfg.transport == "rfcomm":
        from pibot.transport.rfcomm import RfcommTransport

        return RfcommTransport(
            baud=cfg.serial_baud, address=cfg.rfcomm_address, channel=cfg.rfcomm_channel
        )
    if cfg.transport == "ble":
        from pibot.transport.ble import BleTransport

        return BleTransport(cfg.ble_address)
    if cfg.transport == "i2c":
        from pibot.transport.i2c import I2CTransport

        return I2CTransport(cfg.i2c_bus, cfg.i2c_address)
    if cfg.transport == "responder":
        from pibot.transport.responder import ResponderTransport

        return ResponderTransport(cfg.encoding)
    if cfg.transport == "loopback":
        from pibot.transport.loopback import LoopbackTransport

        return LoopbackTransport()
    raise UsageError(f"unknown transport {cfg.transport!r}")


def build_from_config(cfg: Config) -> web.Application:
    """Build the full agent app from configuration."""
    app = build_app(
        transport=build_transport(cfg),
        token=load_token(cfg.agent_token_path),
        trust_loopback=True,
        deadman_ms=cfg.watchdog_ms,
        max_rate_hz=cfg.teleop_rate_hz,
        encoding=cfg.encoding,
    )
    return app


def main() -> int:
    cfg = load_config()
    host, _, port = cfg.agent_bind.partition(":")
    app = build_from_config(cfg)
    print(f"pibotd {__version__} serving on {cfg.agent_bind} (transport={cfg.transport})")
    web.run_app(app, host=host or "127.0.0.1", port=int(port or 8787), print=None)
    return 0
