"""pibotd entrypoint — build the transport from config and serve the agent.

Run on the Pi as ``python -m agent``. Selects the robot transport from config
(``serial`` / ``tcp`` to the ESP32 / ``responder`` for no-hardware dev / ``loopback``),
builds the aiohttp app, and serves it on the configured bind address.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp import web

from agent import __version__
from agent.app import build_app
from agent.auth import load_token
from agent.video import CameraBroker
from pibot.config import Config, load_config
from pibot.errors import PibotError, UsageError
from pibot.logging import get_logger
from pibot.transport.base import Transport

if TYPE_CHECKING:
    from pibot.arm.manager import ArmManager
    from pibot.arm.safety import ArmGate

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


def build_arm(cfg: Config) -> ArmManager | None:
    """Construct the stepper-arm manager from config, or ``None`` when no arm is configured.

    One ``SerialTransport`` per ``arm_serial_ports`` entry (one per board), with
    ``arm_joints_per_board`` giving the joint count on each. The arm imports are lazy so the
    agent core stays free of the arm package until an arm is actually configured.
    """
    if not cfg.arm_serial_ports:
        return None
    if len(cfg.arm_joints_per_board) != len(cfg.arm_serial_ports):
        raise UsageError(
            "arm_joints_per_board must have one entry per arm_serial_ports board "
            f"({len(cfg.arm_joints_per_board)} != {len(cfg.arm_serial_ports)})"
        )
    from pibot.arm.manager import ArmManager, linear_joint_map
    from pibot.transport.serial import SerialTransport

    transports: list[Transport] = [
        SerialTransport(port, cfg.arm_baud) for port in cfg.arm_serial_ports
    ]
    joints = linear_joint_map(cfg.arm_joints_per_board)
    _log.info("arm enabled: %d board(s), %d joint(s)", len(transports), len(joints))
    return ArmManager(transports, joints, encoding=cfg.arm_encoding)


def build_arm_gate(cfg: Config, num_joints: int) -> ArmGate:
    """Construct the host arm safety gate from config's per-joint ``arm_joint_limits``.

    Empty -> a permissive default limit per joint. Otherwise there must be exactly one
    ``[min_deg, max_deg, max_dps]`` triple per logical joint, cross-checked here (mirrors
    :func:`build_arm`'s ports/joints length check) so a miscount fails loudly at startup rather
    than silently mis-clamping a joint.
    """
    from pibot.arm.safety import ArmGate, JointLimit

    if not cfg.arm_joint_limits:
        return ArmGate.with_defaults(num_joints)
    if len(cfg.arm_joint_limits) != num_joints:
        raise UsageError(
            "arm_joint_limits must have one [min_deg,max_deg,max_dps] triple per joint "
            f"({len(cfg.arm_joint_limits)} != {num_joints})"
        )
    limits = [JointLimit(min_deg=t[0], max_deg=t[1], max_dps=t[2]) for t in cfg.arm_joint_limits]
    return ArmGate(limits)


def build_from_config(cfg: Config) -> web.Application:
    """Build the full agent app from configuration."""
    arm = build_arm(cfg)
    arm_gate = build_arm_gate(cfg, arm.num_joints) if arm is not None else None
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
        arm=arm,
        arm_gate=arm_gate,
    )
    return app


def main() -> int:
    cfg = load_config()
    host, _, port = cfg.agent_bind.partition(":")
    app = build_from_config(cfg)
    print(f"pibotd {__version__} serving on {cfg.agent_bind} (transport={cfg.transport})")
    web.run_app(app, host=host or "127.0.0.1", port=int(port or 8787), print=None)
    return 0
