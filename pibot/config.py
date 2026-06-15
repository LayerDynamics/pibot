"""Configuration model and loader for the PiBot Control Suite.

Settings live in ``$PIBOT_CONFIG_DIR/config.toml`` (default ``~/.config/pibot``).
The file is optional — every key has a sensible default — and is validated strictly:
unknown keys and wrong types are rejected with a clear :class:`ConfigError` rather
than silently ignored, so a typo never quietly changes behaviour.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pibot import tomlio
from pibot.errors import ConfigError


@dataclass
class Config:
    """Resolved suite configuration (defaults merged with the user's file)."""

    default_user: str | None = None
    identity: str | None = None
    transport: str = "serial"
    encoding: str = "ascii"
    tcp_port: int = 3333
    robot_host: str = "127.0.0.1"
    serial_port: str = "/dev/ttyACM0"
    serial_baud: int = 115200
    ble_address: str = ""
    i2c_bus: int = 1
    i2c_address: int = 0x08
    rfcomm_address: str = ""
    rfcomm_channel: int = 1
    deploy_base: str = "/opt/pibot"
    cmd_timeout: float = 1.0
    teleop_rate_hz: int = 20
    watchdog_ms: int = 300
    temp_warn_c: float = 80.0
    agent_bind: str = "127.0.0.1:8787"
    agent_token_path: str = ""
    scan_timeout: float = 1.0
    # Autonomy / VLA policy client (SPEC-2 / M7) — the on-robot client connects to a
    # remote policy server (the M4 Max) and drives at control_hz using action chunks.
    policy_host: str = ""
    policy_port: int = 8000
    action_horizon: int = 50
    control_hz: int = 20
    camera_device: str = "/dev/video0"
    prompt: str = ""
    video_fps: int = 10
    video_max_dim: int = 640
    # Stepper arm (SPEC: docs/plans/2026-06-13-pibot-arm-control.md). pibotd owns the
    # ArmManager when arm_serial_ports is non-empty: one serial port per board, with
    # arm_joints_per_board giving the joint count on each (parallel lists, same length).
    arm_serial_ports: list[str] = field(default_factory=list)
    arm_joints_per_board: list[int] = field(default_factory=list)
    arm_baud: int = 115200
    arm_encoding: str = "ascii"
    # Per-logical-joint host safety limits: one ``[min_deg, max_deg, max_dps]`` triple per joint
    # (parallel to the linearised joint map). Empty -> the agent builds permissive defaults. The
    # count is cross-checked against the joint total at gate construction (agent/pibotd.py), not
    # here, mirroring build_arm's serial-ports/joints-per-board length check.
    arm_joint_limits: list[list[float]] = field(default_factory=list)


# The three SPEC-2 behaviors (FR-9): a CLI shorthand (`--task`) -> the canonical prompt the
# policy was fine-tuned on. Keep these strings in lockstep with the demonstration prompts in
# docs/runbooks/data-collection.md.
TASK_PROMPTS: dict[str, str] = {
    "goal": "drive to the red ball",
    "follow": "follow me",
    "explore": "explore the room",
}


# field name -> accepted types. ``(float, int)`` fields accept an int literal and
# coerce it to float. bool is rejected for numeric fields even though it subclasses
# int, so ``teleop_rate_hz = true`` is an error, not 1.
_FIELD_TYPES: dict[str, tuple[type, ...]] = {
    "default_user": (str,),
    "identity": (str,),
    "transport": (str,),
    "encoding": (str,),
    "tcp_port": (int,),
    "robot_host": (str,),
    "serial_port": (str,),
    "serial_baud": (int,),
    "ble_address": (str,),
    "i2c_bus": (int,),
    "i2c_address": (int,),
    "rfcomm_address": (str,),
    "rfcomm_channel": (int,),
    "deploy_base": (str,),
    "cmd_timeout": (float, int),
    "teleop_rate_hz": (int,),
    "watchdog_ms": (int,),
    "temp_warn_c": (float, int),
    "agent_bind": (str,),
    "agent_token_path": (str,),
    "scan_timeout": (float, int),
    "policy_host": (str,),
    "policy_port": (int,),
    "action_horizon": (int,),
    "control_hz": (int,),
    "camera_device": (str,),
    "prompt": (str,),
    "video_fps": (int,),
    "video_max_dim": (int,),
    "arm_baud": (int,),
    "arm_encoding": (str,),
}

# list-valued fields -> required element type. Validated element-wise (and bool is
# rejected for an int list the same way it is for a scalar int field).
_LIST_FIELD_TYPES: dict[str, type] = {
    "arm_serial_ports": str,
    "arm_joints_per_board": int,
}


def _parse_joint_limits(value: object) -> list[list[float]]:
    """Validate ``arm_joint_limits`` — a list of ``[min_deg, max_deg, max_dps]`` numeric triples.

    Element-wise like the other list fields, but with its own branch because the generic machinery
    only handles a flat list of one scalar type. Ints are coerced to float (parallel to the
    ``(float, int)`` scalar fields); bool is rejected even though it subclasses int.
    """
    err = "config key 'arm_joint_limits' must be a list of [min_deg, max_deg, max_dps] numbers"
    if not isinstance(value, list):
        raise ConfigError(err)
    out: list[list[float]] = []
    for triple in value:
        if not isinstance(triple, list) or len(triple) != 3:
            raise ConfigError(err)
        coerced: list[float] = []
        for v in triple:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ConfigError(err)
            coerced.append(float(v))
        out.append(coerced)
    return out


def config_dir() -> Path:
    """Return the active config directory (``$PIBOT_CONFIG_DIR`` or ``~/.config/pibot``)."""
    env = os.environ.get("PIBOT_CONFIG_DIR")
    if env:
        return Path(env)
    return Path.home() / ".config" / "pibot"


def _typenames(types: tuple[type, ...]) -> str:
    return " or ".join(t.__name__ for t in types)


def load_config(path: str | Path | None = None) -> Config:
    """Load and validate configuration, returning a fully-populated :class:`Config`."""
    target = Path(path) if path is not None else config_dir() / "config.toml"
    try:
        raw = tomlio.load(target)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"malformed config at {target}: {exc}") from exc

    cfg = Config()
    for key, value in raw.items():
        if key == "arm_joint_limits":
            cfg.arm_joint_limits = _parse_joint_limits(value)
            continue
        if key in _LIST_FIELD_TYPES:
            elem = _LIST_FIELD_TYPES[key]
            if not isinstance(value, list) or any(
                isinstance(v, bool) or not isinstance(v, elem) for v in value
            ):
                raise ConfigError(f"config key {key!r} must be a list of {elem.__name__}")
            setattr(cfg, key, value)
            continue
        if key not in _FIELD_TYPES:
            raise ConfigError(f"unknown config key: {key!r}")
        types = _FIELD_TYPES[key]
        if isinstance(value, bool) and bool not in types:
            raise ConfigError(f"config key {key!r} must be {_typenames(types)}, got bool")
        if not isinstance(value, types):
            raise ConfigError(
                f"config key {key!r} must be {_typenames(types)}, got {type(value).__name__}"
            )
        if types == (float, int) and isinstance(value, int):
            value = float(value)
        setattr(cfg, key, value)

    if not cfg.agent_token_path:
        cfg.agent_token_path = str(config_dir() / "agent.token")
    return cfg
