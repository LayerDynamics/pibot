"""M-ARM-7 — live stepper-arm integration against the real Pi (opt-in).

Runs only when ``PIBOT_TEST_HOST`` names a reachable Pi and ``PIBOT_TEST_ARM=1`` opts into
physical arm motion. Proves the post-SPEC-4 acceptance bar on real hardware:

  - the arm telemetry + safety surface responds over the real agent link;
  - e-stop/clear and enable/disable work without crashing the arm stack;
  - one configured joint can be homed, jogged briefly, and sent to a conservative absolute move;
  - pose/program CRUD + run/stop persists and reports progress through telemetry;
  - optional gripper/tool hardware can be exercised when explicitly enabled.

Skips cleanly without the bench env so CI stays green.

    PIBOT_TEST_HOST=192.168.1.99 \
    PIBOT_TEST_ARM=1 \
    PIBOT_TEST_ARM_MOVE_DEG=5 \
    .venv/bin/pytest tests/integration/test_arm_live.py -q
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
from pibot.control.client import AgentClient

_HOST = os.environ.get("PIBOT_TEST_HOST")
_ARM = os.environ.get("PIBOT_TEST_ARM")
_GRIPPER = os.environ.get("PIBOT_TEST_ARM_GRIPPER")

_HOME_JOINT = int(os.environ.get("PIBOT_TEST_ARM_HOME_JOINT", "0"))
_JOG_DPS = float(os.environ.get("PIBOT_TEST_ARM_JOG_DPS", "5"))
_JOG_SECONDS = float(os.environ.get("PIBOT_TEST_ARM_JOG_SECONDS", "0.2"))
_MOVE_DEG = float(os.environ.get("PIBOT_TEST_ARM_MOVE_DEG", "5"))
_MOVE_SPEED = float(os.environ.get("PIBOT_TEST_ARM_MOVE_SPEED", "5"))
_WAIT_SECONDS = float(os.environ.get("PIBOT_TEST_ARM_WAIT_SECONDS", "2.0"))
_GRIP_DEG = float(os.environ.get("PIBOT_TEST_ARM_GRIP_DEG", "10"))

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(
        not _HOST or not _ARM,
        reason="set PIBOT_TEST_HOST and PIBOT_TEST_ARM=1 to run live arm tests",
    ),
]


def _token() -> str | None:
    cfg = load_config()
    return os.environ.get("PIBOT_TEST_TOKEN") or load_token(cfg.agent_token_path)


def _base_url() -> str:
    cfg = load_config()
    port = int(cfg.agent_bind.rsplit(":", 1)[1])
    return f"http://{_HOST}:{port}"


async def _open_client() -> AgentClient:
    client = AgentClient(_base_url(), token=_token())
    await client.open()
    return client


async def _eventually(
    fetch: Callable[[], Awaitable[Any]],
    predicate: Callable[[Any], bool],
    *,
    timeout: float = 5.0,
    interval: float = 0.1,
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


def _name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _assert_ack(reply: dict[str, Any]) -> None:
    assert reply == {"type": "ack"}


async def _delete_pose_if_present(client: AgentClient, name: str) -> None:
    with contextlib.suppress(Exception):
        await client.arm_pose_delete(name)


async def _delete_program_if_present(client: AgentClient, name: str) -> None:
    with contextlib.suppress(Exception):
        await client.arm_program_delete(name)


def test_live_arm_motion_surface() -> None:
    async def body() -> None:
        client = await _open_client()
        try:
            snap = await client.arm_telemetry()
            assert snap["enabled"] is True
            assert snap["num_joints"] >= 1
            assert "positions" in snap
            assert "homed" in snap
            assert "estopped" in snap

            joint = _HOME_JOINT
            assert joint < snap["num_joints"], f"joint {joint} is out of range for this stand"

            _assert_ack(await client.arm_enable(True))
            _assert_ack(await client.arm_estop())

            latched = await client.arm_jog(joint, _JOG_DPS)
            assert latched["type"] == "nak"
            assert "estop" in latched["reason"].lower()

            _assert_ack(await client.arm_clear_estop())
            _assert_ack(await client.arm_enable(False))
            _assert_ack(await client.arm_enable(True))
            _assert_ack(await client.arm_home(joint))

            await _eventually(
                client.arm_telemetry,
                lambda t: t["homed"].get(str(joint)) is True,
                description=f"joint {joint} to report homed",
            )

            _assert_ack(await client.arm_jog(joint, _JOG_DPS))
            await asyncio.sleep(_JOG_SECONDS)
            _assert_ack(await client.arm_jog(joint, 0.0))

            _assert_ack(await client.arm_move_joint(joint, _MOVE_DEG, _MOVE_SPEED))
        finally:
            await client.close()

    asyncio.run(body())


def test_live_arm_pose_and_program_surface() -> None:
    async def body() -> None:
        client = await _open_client()
        pose_name = _name("marm7-pose")
        program_name = _name("marm7-program")
        try:
            created_pose = await client.arm_pose_save(pose_name)
            assert created_pose["name"] == pose_name
            listed_poses = await client.arm_pose_list()
            assert any(p["name"] == pose_name for p in listed_poses["poses"])
            fetched_pose = await client.arm_pose_get(pose_name)
            assert fetched_pose["name"] == pose_name

            created_program = await client.arm_program_save(
                {
                    "name": program_name,
                    "steps": [{"kind": "wait", "seconds": _WAIT_SECONDS}],
                }
            )
            assert created_program["name"] == program_name
            listed_programs = await client.arm_program_list()
            assert any(p["name"] == program_name for p in listed_programs["programs"])
            fetched_program = await client.arm_program_get(program_name)
            assert fetched_program["name"] == program_name

            run = await client.arm_program_run(program_name)
            assert run == {"running": True, "name": program_name}

            running = await _eventually(
                client.arm_telemetry,
                lambda t: isinstance(t.get("program"), dict) and t["program"]["state"] == "running",
                description=f"program {program_name} to enter the running state",
            )
            assert running["program"]["name"] == program_name
            assert running["program"]["current_kind"] == "wait"

            assert await client.arm_program_stop() == {"stopped": True}

            stopped = await _eventually(
                client.arm_telemetry,
                lambda t: isinstance(t.get("program"), dict) and t["program"]["state"] == "stopped",
                description=f"program {program_name} to report stopped",
            )
            assert stopped["program"]["name"] == program_name
            assert stopped["program"]["message"] == "stopped"
        finally:
            await _delete_program_if_present(client, program_name)
            await _delete_pose_if_present(client, pose_name)
            await client.close()

    asyncio.run(body())


@pytest.mark.skipif(
    not _GRIPPER,
    reason="set PIBOT_TEST_ARM_GRIPPER=1 on a stand with the optional gripper/tool hardware",
)
def test_live_arm_gripper_and_tool_surface() -> None:
    async def body() -> None:
        client = await _open_client()
        try:
            _assert_ack(await client.arm_estop())
            blocked = await client.arm_grip(_GRIP_DEG)
            assert blocked["type"] == "nak"
            assert "estop" in blocked["reason"].lower()
            _assert_ack(await client.arm_clear_estop())

            _assert_ack(await client.arm_grip(_GRIP_DEG))
            _assert_ack(await client.arm_tool(True))

            grip = await _eventually(
                client.arm_telemetry,
                lambda t: isinstance(t.get("gripper"), dict) and bool(t["gripper"]["tool"]) is True,
                description="gripper telemetry to report the tool on state",
            )
            assert grip["gripper"]["deg"] == _GRIP_DEG
            assert grip["gripper"]["tool"] is True

            _assert_ack(await client.arm_tool(False))
        finally:
            await client.close()

    asyncio.run(body())
