"""Write headless first-boot configuration to a freshly-flashed boot partition.

``rpi-imager --cli`` does not expose hostname/Wi-Fi/SSH/user customisation, so the
suite writes the Raspberry Pi OS Bookworm ``custom.toml`` init file itself (plus an
empty ``ssh`` marker and, when a UART transport is selected, ``enable_uart=1`` in
``config.txt``). Passwords are stored only as a pre-computed crypt hash — never plain.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from pibot import tomlio
from pibot.logging import get_logger

_log = get_logger("firstboot")

RunFn = Callable[[list[str]], str]


def hash_password(plain: str, run: RunFn | None = None) -> str:
    """Return a SHA-512 crypt hash of ``plain`` via ``openssl passwd -6``."""
    runner = run or _default_openssl
    return runner(["openssl", "passwd", "-6", plain]).strip()


def _default_openssl(argv: list[str]) -> str:
    import subprocess

    return subprocess.run(argv, capture_output=True, text=True, check=True).stdout


def write_config(
    boot_dir: str | Path,
    *,
    hostname: str,
    username: str,
    password_hash: str,
    ssh: bool = True,
    wifi_ssid: str | None = None,
    wifi_password: str | None = None,
    wifi_country: str = "US",
    locale_keymap: str | None = None,
    locale_timezone: str | None = None,
    enable_uart: bool = False,
) -> None:
    """Write ``custom.toml`` (+ ssh marker, + config.txt UART) into ``boot_dir``."""
    boot = Path(boot_dir)
    boot.mkdir(parents=True, exist_ok=True)

    config: dict[str, object] = {
        "system": {"hostname": hostname},
        "user": {
            "name": username,
            "password": password_hash,
            "password_encrypted": True,
        },
        "ssh": {"enabled": ssh, "password_authentication": False},
    }
    if wifi_ssid:
        wlan: dict[str, object] = {"ssid": wifi_ssid, "country": wifi_country}
        if wifi_password:
            wlan["password"] = wifi_password
            wlan["password_encrypted"] = False
        config["wlan"] = wlan
    if locale_keymap or locale_timezone:
        locale: dict[str, object] = {}
        if locale_keymap:
            locale["keymap"] = locale_keymap
        if locale_timezone:
            locale["timezone"] = locale_timezone
        config["locale"] = locale

    tomlio.dump(config, boot / "custom.toml")

    if ssh:
        (boot / "ssh").write_text("", encoding="utf-8")

    if enable_uart:
        _append_config_line(boot / "config.txt", "enable_uart=1")

    _log.info("first-boot config written to %s (hostname=%s user=%s)", boot, hostname, username)


def _append_config_line(config_txt: Path, line: str) -> None:
    existing = config_txt.read_text(encoding="utf-8") if config_txt.exists() else ""
    if line in existing.splitlines():
        return
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    config_txt.write_text(prefix + line + "\n", encoding="utf-8")
