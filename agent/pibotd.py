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
from agent.video import CameraBroker
from pibot.config import Config, load_config
from pibot.errors import PibotError, UsageError
from pibot.logging import get_logger
from pibot.transport.base import Transport

_log = get_logger("pibotd")


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


def build_camera_broker(cfg: Config) -> CameraBroker | None:
    """Open the configured USB camera and wrap it in a shared frame broker for ``/video``.

    The broker is the single capture loop the ``/video`` WS endpoint and the autonomy loop
    both subscribe to. Returns ``None`` — leaving video disabled but the agent fully serving —
    when the camera is unavailable: the ml stack (opencv) isn't installed (dev host / CI), no
    camera is attached, or the device is busy. Camera/cv2 imports are lazy so the agent core
    stays free of the ml stack until a camera is actually opened.
    """
    try:
        from pibot.ml.camera import Camera

        camera = Camera(cfg.camera_device)
        camera.open()
    except (ImportError, OSError, PibotError) as exc:
        _log.info("camera %s unavailable (%s); /video disabled", cfg.camera_device, exc)
        return None
    _log.info("camera %s open; /video enabled at %d fps", cfg.camera_device, cfg.video_fps)
    return CameraBroker(camera, fps=cfg.video_fps)


def build_from_config(cfg: Config) -> web.Application:
    """Build the full agent app from configuration."""
    app = build_app(
        transport=build_transport(cfg),
        token=load_token(cfg.agent_token_path),
        trust_loopback=True,
        deadman_ms=cfg.watchdog_ms,
        max_rate_hz=cfg.teleop_rate_hz,
        encoding=cfg.encoding,
        broker=build_camera_broker(cfg),
        video_fps=cfg.video_fps,
        video_max_dim=cfg.video_max_dim,
    )
    return app


def main() -> int:
    cfg = load_config()
    host, _, port = cfg.agent_bind.partition(":")
    app = build_from_config(cfg)
    print(f"pibotd {__version__} serving on {cfg.agent_bind} (transport={cfg.transport})")
    web.run_app(app, host=host or "127.0.0.1", port=int(port or 8787), print=None)
    return 0
