"""M-ARM-1 task 1.5 — ``pibot arm`` CLI: arg parsing + dispatch against a fake AgentClient.

No agent or hardware: a recording fake stands in for ``AgentClient`` so the tests assert the CLI
parses each subcommand and calls the right client method with the right arguments, plus the
``--json`` output shape.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import pibot.cli as cli
from pibot.config import Config


class _Inv:
    def resolve(self, target: str) -> str:
        return "192.168.1.50"


_TELEMETRY = {
    "ok": True,
    "enabled": True,
    "num_joints": 2,
    "positions": {"0": 10.0, "1": 20.0},
    "gripper": None,
    "pose": {"x": 0.5, "y": 0.0, "z": 0.3, "rx": 0.0, "ry": 0.0, "rz": 0.0},
    "ts": 1.0,
    "age_ms": 5.0,
}


class FakeArmClient:
    """Records every arm method call; every motion call acks."""

    last: FakeArmClient | None = None

    def __init__(self, base: str, token: str | None = None) -> None:
        self.base = base
        self.token = token
        self.calls: list[tuple[Any, ...]] = []
        FakeArmClient.last = self

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def arm_telemetry(self) -> dict[str, Any]:
        self.calls.append(("telemetry",))
        return dict(_TELEMETRY)

    async def arm_jog(self, joint: int, dps: float) -> dict[str, Any]:
        self.calls.append(("jog", joint, dps))
        return {"type": "ack"}

    async def arm_move_joint(
        self, joint: int, deg: float, speed: float | None = None
    ) -> dict[str, Any]:
        self.calls.append(("move", joint, deg, speed))
        return {"type": "ack"}

    async def arm_move_joints(self, targets: dict[int, float], seconds: float) -> dict[str, Any]:
        self.calls.append(("move-all", targets, seconds))
        return {"type": "ack"}

    async def arm_home(self, joint: int) -> dict[str, Any]:
        self.calls.append(("home", joint))
        return {"type": "ack"}

    async def arm_estop(self) -> dict[str, Any]:
        self.calls.append(("estop",))
        return {"type": "ack"}

    async def arm_clear_estop(self) -> dict[str, Any]:
        self.calls.append(("clear",))
        return {"type": "ack"}

    async def arm_enable(self, on: bool) -> dict[str, Any]:
        self.calls.append(("enable", on))
        return {"type": "ack"}

    async def arm_grip(self, deg: float) -> dict[str, Any]:
        self.calls.append(("grip", deg))
        return {"type": "ack"}

    async def arm_tool(self, on: bool) -> dict[str, Any]:
        self.calls.append(("tool", on))
        return {"type": "ack"}


@pytest.fixture(autouse=True)
def _wire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "_context", lambda: (Config(), _Inv()))
    monkeypatch.setattr("pibot.control.client.AgentClient", FakeArmClient)
    monkeypatch.setattr("agent.auth.load_token", lambda _path: "tok")
    FakeArmClient.last = None


def _calls() -> list[tuple[Any, ...]]:
    assert FakeArmClient.last is not None
    return FakeArmClient.last.calls


def test_arm_jog_dispatch() -> None:
    assert cli.main(["arm", "jog", "esp32", "1", "25"]) == 0
    assert _calls() == [("jog", 1, 25.0)]


def test_arm_move_without_speed_passes_none() -> None:
    assert cli.main(["arm", "move", "esp32", "0", "30"]) == 0
    assert _calls() == [("move", 0, 30.0, None)]


def test_arm_move_with_speed() -> None:
    assert cli.main(["arm", "move", "esp32", "0", "30", "--speed", "5"]) == 0
    assert _calls() == [("move", 0, 30.0, 5.0)]


def test_arm_move_all_parses_targets() -> None:
    assert cli.main(["arm", "move-all", "esp32", "0=90,1=-45", "--seconds", "2"]) == 0
    assert _calls() == [("move-all", {0: 90.0, 1: -45.0}, 2.0)]


def test_arm_move_all_rejects_bad_target_spec() -> None:
    # 'fast' is not a number -> UsageError (exit 2), no client motion call.
    assert cli.main(["arm", "move-all", "esp32", "0=fast", "--seconds", "2"]) == 2


def test_arm_home_single_joint() -> None:
    assert cli.main(["arm", "home", "esp32", "0"]) == 0
    assert _calls() == [("home", 0)]


def test_arm_home_all_homes_every_joint() -> None:
    assert cli.main(["arm", "home", "esp32", "--all"]) == 0
    # telemetry first (to learn the joint count), then one home per joint.
    assert _calls() == [("telemetry",), ("home", 0), ("home", 1)]


def test_arm_home_requires_joint_or_all() -> None:
    assert cli.main(["arm", "home", "esp32"]) == 2  # neither joint nor --all


def test_arm_estop_clear_enable_disable() -> None:
    assert cli.main(["arm", "estop", "esp32"]) == 0
    assert _calls() == [("estop",)]
    assert cli.main(["arm", "clear", "esp32"]) == 0
    assert _calls() == [("clear",)]
    assert cli.main(["arm", "enable", "esp32"]) == 0
    assert _calls() == [("enable", True)]
    assert cli.main(["arm", "disable", "esp32"]) == 0
    assert _calls() == [("enable", False)]


def test_arm_pose_zero_resolves_to_all_zero_targets() -> None:
    assert cli.main(["arm", "pose", "esp32", "zero", "--seconds", "3"]) == 0
    # telemetry (for joint count) then a synchronized move to every-joint-zero.
    assert _calls() == [("telemetry",), ("move-all", {0: 0.0, 1: 0.0}, 3.0)]


def test_arm_pose_unknown_name_errors() -> None:
    # Only the geometry-free 'zero' preset ships in M-ARM-1; others must error honestly.
    assert cli.main(["arm", "pose", "esp32", "ready"]) == 2


def test_arm_grip_dispatch() -> None:
    assert cli.main(["arm", "grip", "esp32", "40"]) == 0
    assert _calls() == [("grip", 40.0)]


def test_arm_tool_on_and_off() -> None:
    assert cli.main(["arm", "tool", "esp32", "on"]) == 0
    assert _calls() == [("tool", True)]
    assert cli.main(["arm", "tool", "esp32", "off"]) == 0
    assert _calls() == [("tool", False)]


def test_arm_tool_rejects_bad_state() -> None:
    with pytest.raises(SystemExit):  # argparse rejects an out-of-choices value
        cli.main(["arm", "tool", "esp32", "maybe"])


def test_arm_telemetry_json_output_shape(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["arm", "telemetry", "esp32", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["enabled"] is True
    assert out["num_joints"] == 2
    assert out["positions"] == {"0": 10.0, "1": 20.0}


def test_arm_jog_json_output_is_the_reply(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["arm", "jog", "esp32", "0", "10", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"type": "ack"}


def test_arm_dry_run_previews_without_opening_a_client(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["arm", "move", "esp32", "0", "30", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "move joint 0 to 30" in out
    # No AgentClient was constructed — the transport was never opened.
    assert FakeArmClient.last is None


def test_arm_move_all_dry_run_validates_targets() -> None:
    # A bad target spec is rejected even in dry-run (validation happens before any send).
    assert cli.main(["arm", "move-all", "esp32", "oops", "--seconds", "1", "--dry-run"]) == 2


def test_arm_telemetry_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["arm", "telemetry", "esp32"]) == 0
    out = capsys.readouterr().out
    assert "2 joint(s)" in out
    assert "J0: 10.0°" in out
    assert "J1: 20.0°" in out
    assert "EE: x=500 y=0 z=300 mm" in out  # FK pose, metres -> mm


def test_arm_command_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    class SlowClient(FakeArmClient):
        async def arm_jog(self, joint: int, dps: float) -> dict[str, Any]:
            await asyncio.sleep(0.2)
            return {"type": "ack"}

    monkeypatch.setattr("pibot.control.client.AgentClient", SlowClient)
    # --timeout is shorter than the client call -> a clean UsageError (exit 2), not a traceback.
    assert cli.main(["arm", "jog", "esp32", "0", "10", "--timeout", "0.01"]) == 2
