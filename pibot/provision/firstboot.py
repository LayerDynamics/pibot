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
    ssh_authorized_keys: list[str] | None = None,
    wifi_ssid: str | None = None,
    wifi_password: str | None = None,
    wifi_country: str = "US",
    locale_keymap: str | None = None,
    locale_timezone: str | None = None,
    enable_uart: bool = False,
) -> None:
    """Write ``custom.toml`` (+ ssh marker, + config.txt UART) into ``boot_dir``.

    This is the Raspberry Pi OS first-boot mechanism. For Ubuntu images use
    :func:`write_cloud_init`, or :func:`apply_first_boot` to dispatch automatically.
    """
    boot = Path(boot_dir)
    boot.mkdir(parents=True, exist_ok=True)

    ssh_block: dict[str, object] = {"enabled": ssh, "password_authentication": False}
    if ssh_authorized_keys:
        ssh_block["authorized_keys"] = list(ssh_authorized_keys)
    config: dict[str, object] = {
        "system": {"hostname": hostname},
        "user": {
            "name": username,
            "password": password_hash,
            "password_encrypted": True,
        },
        "ssh": ssh_block,
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


def write_cloud_init(
    boot_dir: str | Path,
    *,
    hostname: str,
    username: str,
    ssh_authorized_keys: list[str],
    password_hash: str | None = None,
) -> None:
    """Write Ubuntu cloud-init ``user-data`` + ``meta-data`` into ``boot_dir``.

    Ubuntu Server for Pi uses cloud-init (NoCloud datasource) on the boot partition
    rather than Raspberry Pi OS's ``custom.toml``. This embeds the SSH public key(s)
    so the freshly-flashed Pi is reachable, and disables password SSH.
    """
    boot = Path(boot_dir)
    boot.mkdir(parents=True, exist_ok=True)

    key_lines = "\n".join(f"      - {key}" for key in ssh_authorized_keys)
    password_block = ""
    if password_hash:
        password_block = f"    passwd: {password_hash}\n    lock_passwd: false\n"

    user_data = (
        "#cloud-config\n"
        f"hostname: {hostname}\n"
        "manage_etc_hosts: true\n"
        "ssh_pwauth: false\n"
        "users:\n"
        f"  - name: {username}\n"
        "    groups: [adm, sudo]\n"
        "    shell: /bin/bash\n"
        '    sudo: "ALL=(ALL) NOPASSWD:ALL"\n'
        f"{password_block}"
        "    ssh_authorized_keys:\n"
        f"{key_lines}\n"
    )
    (boot / "user-data").write_text(user_data, encoding="utf-8")
    (boot / "meta-data").write_text(
        f"instance-id: {hostname}\nlocal-hostname: {hostname}\n", encoding="utf-8"
    )
    _log.info("cloud-init user-data written to %s (hostname=%s user=%s)", boot, hostname, username)


def detect_flavor(boot_dir: str | Path) -> str:
    """Return ``"ubuntu"`` if the boot partition uses cloud-init, else ``"rpi-os"``."""
    boot = Path(boot_dir)
    if (boot / "user-data").exists() or (boot / "meta-data").exists():
        return "ubuntu"
    return "rpi-os"


def apply_first_boot(
    boot_dir: str | Path,
    *,
    hostname: str,
    username: str,
    ssh_authorized_keys: list[str],
    password_hash: str | None = None,
    flavor: str | None = None,
    **rpi_os_kwargs: object,
) -> None:
    """Apply first-boot config, dispatching to cloud-init or custom.toml by flavor."""
    chosen = flavor or detect_flavor(boot_dir)
    if chosen == "ubuntu":
        write_cloud_init(
            boot_dir,
            hostname=hostname,
            username=username,
            ssh_authorized_keys=ssh_authorized_keys,
            password_hash=password_hash,
        )
    else:
        write_config(
            boot_dir,
            hostname=hostname,
            username=username,
            password_hash=password_hash or "",
            ssh_authorized_keys=ssh_authorized_keys,
            **rpi_os_kwargs,  # type: ignore[arg-type]
        )
