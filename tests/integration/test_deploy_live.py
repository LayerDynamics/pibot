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

import os

import pytest

from pibot.config import load_config
from pibot.connection import sshcmd, user
from pibot.deploy import service, sync
from pibot.inventory import Inventory, InventoryRecord

_HOST = os.environ.get("PIBOT_TEST_HOST")

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(not _HOST, reason="set PIBOT_TEST_HOST to run live deploy tests"),
]


def _destination(cfg) -> str:
    address = (_HOST or "").strip()
    login = user.resolve_user(address, cfg, explicit=os.environ.get("PIBOT_TEST_USER"))
    return sshcmd.destination(address, login)


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
