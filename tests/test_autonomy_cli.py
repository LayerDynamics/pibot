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

from pibot.cli import _autonomy_limits, build_parser, cmd_autonomy
from pibot.config import Config
from pibot.control.safety import Limits


def _parse(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def test_run_and_dry_run_flags_parse() -> None:
    args = _parse(["autonomy", "pibot", "--run", "--dry-run", "--max-speed", "0.4"])
    assert args.run is True
    assert args.dry_run is True
    assert args.max_speed == 0.4


def test_dry_run_previews_without_touching_hardware(monkeypatch, capsys) -> None:
    # If the closed-loop runner were invoked it would open a transport/camera — assert it is NOT.
    import pibot.cli as cli

    def _boom(*a, **k):  # pragma: no cover - must never be called on a dry run
        raise AssertionError("dry-run must not start the closed-loop runner")

    monkeypatch.setattr(
        cli, "_context", lambda: (Config(policy_host="mac", policy_port=8000), _Inv())
    )
    monkeypatch.setattr("pibot.ml.closed_loop.run_closed_loop", _boom, raising=False)

    args = _parse(
        ["autonomy", "pibot", "--run", "--dry-run", "--prompt", "go", "--max-speed", "0.5"]
    )
    rc = cmd_autonomy(args)

    out = capsys.readouterr().out
    assert rc == 0
    assert "dry-run" in out
    assert "mac:8000" in out  # the policy server it would connect to
    assert "0.5" in out  # the speed cap it would enforce


def test_max_speed_only_lowers_the_cap_never_raises_it() -> None:
    base = Limits()  # max_v=1.0
    # a tighter governor is honoured...
    assert _autonomy_limits(0.3).max_v == pytest.approx(0.3)
    # ...but you cannot drive faster than the hardware limit by asking for more.
    assert _autonomy_limits(5.0).max_v == base.max_v
    # no cap given -> the default limits.
    assert _autonomy_limits(None).max_v == base.max_v
    assert _autonomy_limits(None).max_w == base.max_w


def test_run_without_dry_run_needs_a_policy_host(monkeypatch) -> None:
    import pibot.cli as cli
    from pibot.errors import UsageError

    monkeypatch.setattr(cli, "_context", lambda: (Config(policy_host=""), _Inv()))
    args = _parse(["autonomy", "pibot", "--run"])
    with pytest.raises(UsageError, match="policy"):
        cmd_autonomy(args)


class _Inv:
    def resolve(self, target: str) -> str:
        return "192.168.1.99"
