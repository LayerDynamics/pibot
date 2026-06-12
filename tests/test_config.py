"""T0.3 — configuration loading: defaults, overrides, and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pibot import tomlio
from pibot.config import Config, config_dir, load_config
from pibot.errors import ConfigError


def test_config_dir_honors_env(isolated_config_dir: str) -> None:
    assert config_dir() == Path(isolated_config_dir)


def test_defaults_when_no_file(isolated_config_dir: str) -> None:
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.transport == "serial"
    assert cfg.teleop_rate_hz == 20
    assert cfg.watchdog_ms == 300
    assert cfg.default_user is None
    # Token path defaults inside the active config dir.
    assert cfg.agent_token_path == str(Path(isolated_config_dir) / "agent.token")


def test_user_overrides_merge_over_defaults(isolated_config_dir: str) -> None:
    path = Path(isolated_config_dir) / "config.toml"
    tomlio.dump({"default_user": "ryan", "teleop_rate_hz": 30, "temp_warn_c": 75.0}, path)
    cfg = load_config()
    assert cfg.default_user == "ryan"
    assert cfg.teleop_rate_hz == 30
    assert cfg.temp_warn_c == 75.0
    # Untouched keys keep their defaults.
    assert cfg.watchdog_ms == 300


def test_unknown_key_is_rejected(isolated_config_dir: str) -> None:
    path = Path(isolated_config_dir) / "config.toml"
    tomlio.dump({"definitely_not_a_setting": 1}, path)
    with pytest.raises(ConfigError) as exc:
        load_config()
    assert "definitely_not_a_setting" in str(exc.value)


# ---- T7.2: ML / autonomy config fields ------------------------------------


def test_ml_config_defaults(isolated_config_dir: str) -> None:
    cfg = load_config()
    assert cfg.policy_host == ""
    assert cfg.policy_port == 8000
    assert cfg.action_horizon == 50
    assert cfg.control_hz == 20
    assert cfg.camera_device == "/dev/video0"
    assert cfg.prompt == ""


def test_ml_config_overrides(isolated_config_dir: str) -> None:
    path = Path(isolated_config_dir) / "config.toml"
    tomlio.dump(
        {
            "policy_host": "192.168.100.1",
            "policy_port": 9000,
            "action_horizon": 10,
            "control_hz": 30,
            "camera_device": "/dev/video1",
            "prompt": "follow me",
        },
        path,
    )
    cfg = load_config()
    assert cfg.policy_host == "192.168.100.1"
    assert cfg.policy_port == 9000
    assert cfg.action_horizon == 10
    assert cfg.control_hz == 30
    assert cfg.camera_device == "/dev/video1"
    assert cfg.prompt == "follow me"


def test_ml_config_wrong_type_rejected(isolated_config_dir: str) -> None:
    path = Path(isolated_config_dir) / "config.toml"
    tomlio.dump({"action_horizon": "fifty"}, path)
    with pytest.raises(ConfigError):
        load_config()


def test_wrong_type_is_rejected(isolated_config_dir: str) -> None:
    path = Path(isolated_config_dir) / "config.toml"
    tomlio.dump({"teleop_rate_hz": "fast"}, path)
    with pytest.raises(ConfigError) as exc:
        load_config()
    assert "teleop_rate_hz" in str(exc.value)


def test_malformed_toml_is_rejected(isolated_config_dir: str) -> None:
    path = Path(isolated_config_dir) / "config.toml"
    path.write_text("this = = broken", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config()


def test_explicit_path_overrides_default(tmp_path: Path) -> None:
    path = tmp_path / "custom.toml"
    tomlio.dump({"transport": "tcp"}, path)
    cfg = load_config(path)
    assert cfg.transport == "tcp"
