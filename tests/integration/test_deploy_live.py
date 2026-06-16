"""T5.7 — live deploy + wireless-drive integration against the real Pi (opt-in).

Runs only when ``PIBOT_TEST_HOST`` names a reachable Pi (SSH key installed). Proves the
M5 acceptance bar on real hardware:

  - ``deploy --restart`` syncs a fresh release and the agent passes ``/health``;
  - ``deploy --rollback`` restores the previous release and the agent stays healthy;
  - (optional) a wireless backend drives the real robot when ``PIBOT_TEST_BLE`` /
    ``PIBOT_TEST_RFCOMM`` names its address.

Skips cleanly without hardware so CI stays green.

    PIBOT_TEST_HOST=192.168.1.99 .venv/bin/pytest tests/integration/test_deploy_live.py
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

import pytest

from agent.auth import load_token
from pibot.config import load_config
from pibot.connection import sshcmd, user
from pibot.control.client import AgentClient
from pibot.deploy import service, sync
from pibot.inventory import Inventory, InventoryRecord

_HOST = os.environ.get("PIBOT_TEST_HOST")
_ARM = os.environ.get("PIBOT_TEST_ARM")

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not _HOST, reason="set PIBOT_TEST_HOST to run live deploy tests"),
]


def _destination(cfg) -> str:
    address = (_HOST or "").strip()
    login = user.resolve_user(address, cfg, explicit=os.environ.get("PIBOT_TEST_USER"))
    return sshcmd.destination(address, login)


def _agent_base(cfg) -> str:
    port = int(cfg.agent_bind.rsplit(":", 1)[1])
    return f"http://{_HOST}:{port}"


def _agent_token(cfg) -> str | None:
    return os.environ.get("PIBOT_TEST_TOKEN") or load_token(cfg.agent_token_path)


def _arm_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


async def _eventually(
    fetch: Callable[[], Awaitable[Any]],
    predicate: Callable[[Any], bool],
    *,
    timeout: float = 10.0,
    interval: float = 0.2,
    description: str,
) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = await fetch()
        if predicate(last):
            return last
        await asyncio.sleep(interval)
    raise AssertionError(f"timed out waiting for {description}; last value: {last!r}")


async def _open_agent_client(cfg) -> AgentClient:
    client = AgentClient(_agent_base(cfg), token=_agent_token(cfg))
    await client.open()
    return client


async def _assert_arm_surface_survives(client: AgentClient) -> None:
    pose_name = _arm_name("deploy-arm-pose")
    program_name = _arm_name("deploy-arm-program")
    try:
        snap = await client.arm_telemetry()
        assert snap["enabled"] is True
        assert "positions" in snap
        assert "homed" in snap
        assert "estopped" in snap

        created_pose = await client.arm_pose_save(pose_name)
        assert created_pose["name"] == pose_name
        listed_poses = await client.arm_pose_list()
        assert any(p["name"] == pose_name for p in listed_poses["poses"])
        assert (await client.arm_pose_get(pose_name))["name"] == pose_name

        created_program = await client.arm_program_save(
            {"name": program_name, "steps": [{"kind": "wait", "seconds": 1.0}]}
        )
        assert created_program["name"] == program_name
        listed_programs = await client.arm_program_list()
        assert any(p["name"] == program_name for p in listed_programs["programs"])
        assert (await client.arm_program_get(program_name))["name"] == program_name
        assert await client.arm_program_run(program_name) == {"running": True, "name": program_name}

        running = await _eventually(
            client.arm_telemetry,
            lambda t: isinstance(t.get("program"), dict) and t["program"]["state"] == "running",
            description=f"program {program_name} to report running after deploy",
        )
        assert running["program"]["name"] == program_name
        assert await client.arm_program_stop() == {"stopped": True}

        stopped = await _eventually(
            client.arm_telemetry,
            lambda t: isinstance(t.get("program"), dict) and t["program"]["state"] == "stopped",
            description=f"program {program_name} to report stopped after deploy",
        )
        assert stopped["program"]["name"] == program_name

        pose = snap.get("pose")
        if isinstance(pose, dict):
            reply = await client.arm_move_cartesian(
                pose["x"],
                pose["y"],
                pose["z"],
                seconds=0.2,
                rx=pose.get("rx", 0.0),
                ry=pose.get("ry", 0.0),
                rz=pose.get("rz", 0.0),
            )
            assert reply["type"] in {"ack", "nak"}
            if reply["type"] == "nak":
                assert any(
                    token in reply["reason"] for token in ("IK unavailable", "homed", "unreachable")
                )
        else:
            reply = await client.arm_move_cartesian(0.0, 0.0, 0.0, seconds=0.2)
            assert reply["type"] == "nak"
            assert "IK unavailable" in reply["reason"]
    finally:
        with contextlib.suppress(Exception):
            await client.arm_program_delete(program_name)
        with contextlib.suppress(Exception):
            await client.arm_pose_delete(pose_name)


def test_deploy_restart_then_rollback() -> None:
    cfg = load_config()
    inv = Inventory(path=None)
    inv.add(InventoryRecord(alias="pibot", ip=_HOST or ""))
    destination = _destination(cfg)
    base = os.environ.get("PIBOT_TEST_DEPLOY_BASE", "/opt/pibot")
    port = int(cfg.agent_bind.rsplit(":", 1)[1])
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 1) deploy a fresh release and bring the agent up
    result = sync.deploy(destination, src_root=repo + "/", remote_base=base)
    assert result.activated
    assert service.install(destination, remote_base=base, port=port) == 0

    # 2) deploy a second release so there is something to roll back to
    sync.deploy(destination, src_root=repo + "/", remote_base=base)
    assert service.install(destination, remote_base=base, port=port) == 0

    # 3) rollback restores the previous release and the agent stays healthy
    assert service.rollback(destination, remote_base=base, port=port) == 0


@pytest.mark.skipif(
    not _ARM,
    reason="set PIBOT_TEST_ARM=1 on an arm-equipped stand to verify arm deploy/rollback",
)
def test_deploy_restart_then_rollback_preserves_arm_surface() -> None:
    cfg = load_config()
    destination = _destination(cfg)
    base = os.environ.get("PIBOT_TEST_DEPLOY_BASE", "/opt/pibot")
    port = int(cfg.agent_bind.rsplit(":", 1)[1])
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    result = sync.deploy(destination, src_root=repo + "/", remote_base=base)
    assert result.activated
    assert service.install(destination, remote_base=base, port=port) == 0

    async def _first_release() -> None:
        client = await _open_agent_client(cfg)
        try:
            await _assert_arm_surface_survives(client)
        finally:
            await client.close()

    asyncio.run(_first_release())

    sync.deploy(destination, src_root=repo + "/", remote_base=base)
    assert service.install(destination, remote_base=base, port=port) == 0
    assert service.rollback(destination, remote_base=base, port=port) == 0

    async def _rollback_release() -> None:
        client = await _open_agent_client(cfg)
        try:
            await _assert_arm_surface_survives(client)
        finally:
            await client.close()

    asyncio.run(_rollback_release())


@pytest.mark.skipif(
    not os.environ.get("PIBOT_TEST_BLE") and not os.environ.get("PIBOT_TEST_RFCOMM"),
    reason="set PIBOT_TEST_BLE or PIBOT_TEST_RFCOMM to a robot BT address to drive over wireless",
)
def test_wireless_backend_drives_real_robot() -> None:
    import asyncio

    from pibot.protocol.codec import Message, MessageType, decode
    from pibot.transport.base import Transport

    def _backend() -> Transport:
        if addr := os.environ.get("PIBOT_TEST_BLE"):
            from pibot.transport.ble import BleTransport

            return BleTransport(addr)
        from pibot.transport.rfcomm import RfcommTransport

        return RfcommTransport(address=os.environ["PIBOT_TEST_RFCOMM"])

    async def body() -> None:
        t = _backend()
        t.open()
        try:
            t.send(_encode("ping", {}))
            # the robot answers (ACK or telemetry) over the wireless link
            got = await asyncio.to_thread(t.recv, 2.0)
            assert got is not None, "no reply over the wireless link"
            decode(got, "ascii")
            # drive briefly, then stop
            t.send(_encode("drive", {"v": 0.2, "w": 0.0}))
            await asyncio.sleep(0.5)
            t.send(_encode("stop", {}))
        finally:
            t.close()
            assert t.is_open is False

    def _encode(name: str, args: dict) -> bytes:
        from pibot.protocol.codec import encode

        return encode(Message(MessageType.COMMAND, 1, name, args), "ascii")

    asyncio.run(body())
