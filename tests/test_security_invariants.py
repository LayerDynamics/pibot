"""T6.5 — security & secrets invariants that must hold for the whole suite.

These are guardrails, not feature tests: a regression here (a token written world-
readable, a secret committed, the disk guard weakened, the agent trusting an
unauthenticated remote) is a security incident, so each invariant is asserted directly.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent.app import build_app
from agent.auth import generate_token, is_loopback, load_token, token_ok
from pibot.errors import PibotError
from pibot.provision.devices import BlockDevice, assert_safe_target

REPO = Path(__file__).resolve().parent.parent


# ---- secret files are never world-readable -------------------------------


def test_generated_token_is_0600(tmp_path) -> None:
    p = tmp_path / "agent.token"
    token = generate_token(p)
    assert token and load_token(p) == token
    mode = p.stat().st_mode & 0o777
    assert mode == 0o600, f"token file mode {oct(mode)} must be 0600"


def test_generate_token_is_idempotent(tmp_path) -> None:
    p = tmp_path / "agent.token"
    first = generate_token(p)
    second = generate_token(p)
    assert first == second  # never clobber an existing shared secret


def test_generate_token_creates_parent_dir_0600(tmp_path) -> None:
    p = tmp_path / "nested" / "dir" / "agent.token"
    generate_token(p)
    assert (p.stat().st_mode & 0o777) == 0o600


# ---- nothing secret is tracked by git ------------------------------------


def test_no_secrets_tracked_by_git() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True
    ).stdout.split()
    bad = [
        f
        for f in tracked
        if f.endswith(".token")
        or f.endswith("_ed25519")
        or f.endswith("_ed25519.pub")
        or "inventory.local" in f
    ]
    assert not bad, f"secret-looking files tracked by git: {bad}"


def test_gitignore_excludes_secrets() -> None:
    gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("*.token", "*_ed25519", ".config/", "inventory.local.toml"):
        assert pattern in gitignore, f".gitignore missing {pattern!r}"


# ---- the agent authenticates non-loopback peers --------------------------


def test_token_check_is_strict() -> None:
    assert is_loopback("127.0.0.1") is True
    assert is_loopback("::1") is True
    assert is_loopback("192.168.1.50") is False
    assert is_loopback(None) is False
    assert token_ok(None, "secret") is False
    assert token_ok("Bearer wrong", "secret") is False
    assert token_ok("secret", "secret") is False  # missing the Bearer scheme
    assert token_ok("Bearer secret", "secret") is True
    assert token_ok("Bearer secret", None) is False  # no server token -> deny


def test_agent_refuses_unauthenticated_non_loopback() -> None:
    """With loopback trust off, an un-tokened request is rejected; a valid token passes."""
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    async def body() -> None:
        app = build_app(transport=_responder(), token="s3cret", trust_loopback=False, max_rate_hz=0)
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            # /healthz stays public (liveness)
            assert (await client.get("/healthz")).status == 200
            # a protected route without a token is rejected
            assert (await client.get("/health")).status == 401
            # ... and accepted with the right bearer token
            ok = await client.get("/health", headers={"Authorization": "Bearer s3cret"})
            assert ok.status == 200
        finally:
            await client.close()

    asyncio.run(body())


def _responder():
    from pibot.transport.responder import ResponderTransport

    return ResponderTransport()


# ---- the wrong-disk guard refuses dangerous targets ----------------------


def _disk(**kw) -> BlockDevice:
    base = dict(
        node="/dev/diskX", size_bytes=32_000_000_000, model="USB", removable=True, internal=False
    )
    base.update(kw)
    return BlockDevice(**base)


def test_guard_refuses_system_disk() -> None:
    with pytest.raises(PibotError, match="system disk"):
        assert_safe_target(_disk(node="/dev/disk0", is_system=True))


def test_guard_refuses_root_mounted_disk() -> None:
    with pytest.raises(PibotError, match="system disk"):
        assert_safe_target(_disk(node="/dev/disk0", mountpoints=["/"]))


def test_guard_refuses_internal_disk() -> None:
    with pytest.raises(PibotError, match="internal disk"):
        assert_safe_target(_disk(node="/dev/nvme0n1", internal=True))


def test_guard_allows_external_removable() -> None:
    assert_safe_target(_disk(node="/dev/disk4", removable=True, internal=False))  # no raise


def test_guard_refuses_wrong_size() -> None:
    with pytest.raises(PibotError, match="does not match"):
        assert_safe_target(_disk(size_bytes=2_000_000_000_000), expected_size=32_000_000_000)
