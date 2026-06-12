"""T1.2 — SSH default-user resolution from the server banner."""

from __future__ import annotations

from pibot.config import Config
from pibot.connection import user


def test_user_from_banner() -> None:
    assert user.user_from_banner("SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13.16") == "ubuntu"
    assert user.user_from_banner("SSH-2.0-OpenSSH_9.2p1 Raspbian-2") == "pi"
    assert user.user_from_banner("SSH-2.0-OpenSSH_9.2p1 Debian-2+deb12u2") == "pi"
    assert user.user_from_banner("SSH-2.0-OpenSSH_for_Windows_8.1") is None
    assert user.user_from_banner("") is None


def test_resolve_user_explicit_wins() -> None:
    cfg = Config(default_user="ryan")
    assert user.resolve_user("h", cfg, explicit="bob", banner_fn=lambda a: "Ubuntu") == "bob"


def test_resolve_user_from_banner() -> None:
    cfg = Config()
    got = user.resolve_user("h", cfg, banner_fn=lambda a: "SSH-2.0-OpenSSH Ubuntu")
    assert got == "ubuntu"


def test_resolve_user_falls_back_to_config_default() -> None:
    cfg = Config(default_user="ryan")
    assert user.resolve_user("h", cfg, banner_fn=lambda a: "") == "ryan"


def test_resolve_user_final_fallback_is_pi() -> None:
    cfg = Config()  # no default_user
    assert user.resolve_user("h", cfg, banner_fn=lambda a: "") == "pi"
