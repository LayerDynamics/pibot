"""Configuration model and loader for the PiBot Control Suite.

Settings live in ``$PIBOT_CONFIG_DIR/config.toml`` (default ``~/.config/pibot``).
The file is optional — every key has a sensible default — and is validated strictly:
unknown keys and wrong types are rejected with a clear :class:`ConfigError` rather
than silently ignored, so a typo never quietly changes behaviour.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
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
    serial_port: str = "/dev/ttyACM0"
    serial_baud: int = 115200
    cmd_timeout: float = 1.0
    teleop_rate_hz: int = 20
    watchdog_ms: int = 300
    temp_warn_c: float = 80.0
    agent_bind: str = "127.0.0.1:8787"
    agent_token_path: str = ""
    scan_timeout: float = 1.0


# field name -> accepted types. ``(float, int)`` fields accept an int literal and
# coerce it to float. bool is rejected for numeric fields even though it subclasses
# int, so ``teleop_rate_hz = true`` is an error, not 1.
_FIELD_TYPES: dict[str, tuple[type, ...]] = {
    "default_user": (str,),
    "identity": (str,),
    "transport": (str,),
    "encoding": (str,),
    "tcp_port": (int,),
    "serial_port": (str,),
    "serial_baud": (int,),
    "cmd_timeout": (float, int),
    "teleop_rate_hz": (int,),
    "watchdog_ms": (int,),
    "temp_warn_c": (float, int),
    "agent_bind": (str,),
    "agent_token_path": (str,),
    "scan_timeout": (float, int),
}


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
