"""First-boot SSH-key embedding for both Raspberry Pi OS and Ubuntu (cloud-init)."""

from __future__ import annotations

from pathlib import Path

from pibot import tomlio
from pibot.provision import firstboot

KEY = "ssh-ed25519 AAAAC3Nz...proton.me"


def test_authorized_keys_in_custom_toml(tmp_path: Path) -> None:
    firstboot.write_config(
        tmp_path,
        hostname="pibot",
        username="pi",
        password_hash="$6$h",
        ssh_authorized_keys=[KEY],
    )
    data = tomlio.load(tmp_path / "custom.toml")
    assert data["ssh"]["authorized_keys"] == [KEY]
    assert data["ssh"]["enabled"] is True


def test_write_cloud_init_embeds_key(tmp_path: Path) -> None:
    firstboot.write_cloud_init(
        tmp_path, hostname="pibot", username="ubuntu", ssh_authorized_keys=[KEY]
    )
    user_data = (tmp_path / "user-data").read_text()
    assert user_data.splitlines()[0] == "#cloud-config"  # cloud-init requires this header
    assert "hostname: pibot" in user_data
    assert "name: ubuntu" in user_data
    assert KEY in user_data
    assert "ssh_pwauth: false" in user_data
    # meta-data must exist for the NoCloud datasource
    meta = (tmp_path / "meta-data").read_text()
    assert "instance-id: pibot" in meta


def test_cloud_init_optional_password(tmp_path: Path) -> None:
    firstboot.write_cloud_init(
        tmp_path,
        hostname="pibot",
        username="ubuntu",
        ssh_authorized_keys=[KEY],
        password_hash="$6$salt$hash",
    )
    user_data = (tmp_path / "user-data").read_text()
    assert "passwd: $6$salt$hash" in user_data


def test_detect_flavor_ubuntu(tmp_path: Path) -> None:
    (tmp_path / "user-data").write_text("#cloud-config\n")
    (tmp_path / "meta-data").write_text("")
    assert firstboot.detect_flavor(tmp_path) == "ubuntu"


def test_detect_flavor_rpi_os(tmp_path: Path) -> None:
    (tmp_path / "config.txt").write_text("")
    (tmp_path / "cmdline.txt").write_text("")
    assert firstboot.detect_flavor(tmp_path) == "rpi-os"


def test_apply_first_boot_dispatches_by_flavor(tmp_path: Path) -> None:
    # Ubuntu boot partition -> cloud-init user-data
    (tmp_path / "meta-data").write_text("")
    firstboot.apply_first_boot(
        tmp_path, hostname="pibot", username="ubuntu", ssh_authorized_keys=[KEY]
    )
    assert KEY in (tmp_path / "user-data").read_text()

    # Raspberry Pi OS boot partition -> custom.toml
    rpi = tmp_path / "rpi"
    rpi.mkdir()
    (rpi / "config.txt").write_text("")
    firstboot.apply_first_boot(
        rpi,
        hostname="pibot",
        username="pi",
        ssh_authorized_keys=[KEY],
        password_hash="$6$h",
    )
    assert KEY in tomlio.load(rpi / "custom.toml")["ssh"]["authorized_keys"]
