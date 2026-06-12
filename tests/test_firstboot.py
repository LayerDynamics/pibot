"""T2.4 — headless first-boot config written to the boot partition."""

from __future__ import annotations

from pathlib import Path

from pibot import tomlio
from pibot.provision import firstboot


def test_writes_custom_toml_with_system_and_ssh(tmp_path: Path) -> None:
    firstboot.write_config(
        tmp_path, hostname="pibot", username="ubuntu", password_hash="$6$abc$xyz", ssh=True
    )
    data = tomlio.load(tmp_path / "custom.toml")
    assert data["system"]["hostname"] == "pibot"
    assert data["user"]["name"] == "ubuntu"
    assert data["user"]["password"] == "$6$abc$xyz"
    assert data["user"]["password_encrypted"] is True
    assert data["ssh"]["enabled"] is True
    # belt-and-suspenders SSH enable file also present
    assert (tmp_path / "ssh").exists()


def test_wifi_block_written_when_given(tmp_path: Path) -> None:
    firstboot.write_config(
        tmp_path,
        hostname="pibot",
        username="pi",
        password_hash="$6$h",
        wifi_ssid="MyNet",
        wifi_password="secret",
        wifi_country="US",
    )
    data = tomlio.load(tmp_path / "custom.toml")
    assert data["wlan"]["ssid"] == "MyNet"
    assert data["wlan"]["country"] == "US"


def test_no_wifi_block_when_absent(tmp_path: Path) -> None:
    firstboot.write_config(tmp_path, hostname="pibot", username="pi", password_hash="$6$h")
    assert "wlan" not in tomlio.load(tmp_path / "custom.toml")


def test_enable_uart_appends_to_config_txt(tmp_path: Path) -> None:
    (tmp_path / "config.txt").write_text("# existing\ndtparam=audio=on\n", encoding="utf-8")
    firstboot.write_config(
        tmp_path, hostname="pibot", username="pi", password_hash="$6$h", enable_uart=True
    )
    cfg = (tmp_path / "config.txt").read_text()
    assert "enable_uart=1" in cfg
    assert "dtparam=audio=on" in cfg  # preserves existing content


def test_enable_uart_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "config.txt").write_text("enable_uart=1\n", encoding="utf-8")
    firstboot.write_config(
        tmp_path, hostname="pibot", username="pi", password_hash="$6$h", enable_uart=True
    )
    assert (tmp_path / "config.txt").read_text().count("enable_uart=1") == 1


def test_hash_password_uses_openssl(monkeypatch) -> None:
    seen = {}

    def fake_run(argv):
        seen["argv"] = argv
        return "$6$salt$hashed\n"

    out = firstboot.hash_password("hunter2", run=fake_run)
    assert out == "$6$salt$hashed"
    assert seen["argv"][:3] == ["openssl", "passwd", "-6"]
