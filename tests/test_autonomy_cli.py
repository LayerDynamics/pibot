"""T10.4 — `pibot autonomy --run`: the closed-loop CLI and its --dry-run preview.

`--run` is the actuating mode: the remote VLA drives the robot through the M4 safety gate.
Because it mutates the world, it must support `--dry-run` — print exactly what it *would* do
(target, policy server, speed cap, control rate) while opening no transport, camera, or socket.
The hardware loop itself (`pibot.ml.closed_loop.run_closed_loop`) is exercised on the robot;
here we pin the dry-run preview and the speed-governor math, which need no hardware.
"""

from __future__ import annotations

import argparse

import pytest

from pibot.cli import _autonomy_limits, _resolve_prompt, build_parser, cmd_autonomy
from pibot.config import TASK_PROMPTS, Config
from pibot.control.safety import Limits
from pibot.ml.closed_loop import ClosedLoopEnvironment


def _parse(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def test_run_and_dry_run_flags_parse() -> None:
    args = _parse(["autonomy", "pibot", "--run", "--dry-run", "--max-speed", "0.4"])
    assert args.run is True
    assert args.dry_run is True
    assert args.max_speed == 0.4


def test_dry_run_previews_without_touching_the_agent(monkeypatch, capsys) -> None:
    # --run drives via pibotd; --dry-run must print the plan and contact the agent NOT at all.
    import pibot.cli as cli

    def _boom(*a, **k):  # pragma: no cover - must never be called on a dry run
        raise AssertionError("dry-run must not contact the agent")

    monkeypatch.setattr(cli, "_context", lambda: (Config(), _Inv()))
    monkeypatch.setattr(cli, "_drive_via_agent", _boom)

    args = _parse(
        ["autonomy", "pibot", "--run", "--dry-run", "--prompt", "go", "--max-speed", "0.5"]
    )
    rc = cmd_autonomy(args)

    out = capsys.readouterr().out
    assert rc == 0
    assert "dry-run" in out
    assert "192.168.1.99" in out  # the robot it would drive (via pibotd)
    assert "0.5" in out  # the speed cap it would enforce
    assert "go" in out  # the prompt


def test_max_speed_only_lowers_the_cap_never_raises_it() -> None:
    base = Limits()  # max_v=1.0
    # a tighter governor is honoured...
    assert _autonomy_limits(0.3).max_v == pytest.approx(0.3)
    # ...but you cannot drive faster than the hardware limit by asking for more.
    assert _autonomy_limits(5.0).max_v == base.max_v
    # no cap given -> the default limits.
    assert _autonomy_limits(None).max_v == base.max_v
    assert _autonomy_limits(None).max_w == base.max_w


def test_run_dispatches_to_the_agent(monkeypatch) -> None:
    # Without --dry-run, --run hands prompt + governor to the agent driver (pibotd owns the loop).
    import pibot.cli as cli

    called: dict = {}

    def _fake_drive(cfg, inv, target, prompt, max_speed):
        called.update(target=target, prompt=prompt, max_speed=max_speed)
        return 0

    monkeypatch.setattr(cli, "_context", lambda: (Config(), _Inv()))
    monkeypatch.setattr(cli, "_drive_via_agent", _fake_drive)
    args = _parse(["autonomy", "pibot", "--run", "--prompt", "go fast", "--max-speed", "0.3"])
    assert cmd_autonomy(args) == 0
    assert called == {"target": "pibot", "prompt": "go fast", "max_speed": 0.3}


class _Inv:
    def resolve(self, target: str) -> str:
        return "192.168.1.99"


# ---- T11.3: per-task prompt support (FR-9) ------------------------------


class _Cam:
    def capture(self) -> str:
        return "IMG"


def test_task_shorthand_maps_to_canonical_prompt() -> None:
    for task, expected in TASK_PROMPTS.items():
        args = _parse(["autonomy", "pibot", "--run", "--task", task])
        assert _resolve_prompt(args, Config()) == expected


def test_explicit_prompt_overrides_task() -> None:
    args = _parse(["autonomy", "pibot", "--run", "--task", "goal", "--prompt", "custom thing"])
    assert _resolve_prompt(args, Config()) == "custom thing"


def test_resolve_prompt_falls_back_to_config_prompt() -> None:
    args = _parse(["autonomy", "pibot", "--run"])  # neither --task nor --prompt
    assert _resolve_prompt(args, Config(prompt="from config")) == "from config"


def test_only_the_three_tasks_are_accepted() -> None:
    with pytest.raises(SystemExit):  # argparse rejects an unknown choice
        _parse(["autonomy", "pibot", "--run", "--task", "fly"])


def test_runner_forwards_prompt_into_every_observation() -> None:
    # The resolved prompt must ride in each observation the policy sees.
    env = ClosedLoopEnvironment(
        _Cam(),
        state_fn=lambda: [0.0, 0.0],
        prompt=TASK_PROMPTS["follow"],
        submit=lambda m: (True, "ok"),
    )
    assert env.get_observation()["prompt"] == "follow me"
