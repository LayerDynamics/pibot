"""T8.5 — `pibot autonomy --open-loop` dispatch (no actuation; closed-loop is M10)."""

from __future__ import annotations

import pibot.cli as cli
from pibot.config import Config


class _Inv:
    def resolve(self, target: str) -> str:
        return "192.168.1.99"


def _ctx(monkeypatch, cfg: Config | None = None) -> None:
    monkeypatch.setattr(cli, "_context", lambda: (cfg or Config(), _Inv()))


def test_open_loop_dispatch_passes_target_and_prompt(monkeypatch) -> None:
    seen: dict = {}
    _ctx(monkeypatch, Config(prompt="default"))
    monkeypatch.setattr(
        cli, "_run_open_loop", lambda cfg, inv, target, prompt: seen.update(t=target, p=prompt) or 0
    )
    rc = cli.main(["autonomy", "esp32", "--open-loop", "--prompt", "drive to the red ball"])
    assert rc == 0
    assert seen == {"t": "esp32", "p": "drive to the red ball"}


def test_open_loop_falls_back_to_config_prompt(monkeypatch) -> None:
    seen: dict = {}
    _ctx(monkeypatch, Config(prompt="follow me"))
    monkeypatch.setattr(
        cli, "_run_open_loop", lambda cfg, inv, target, prompt: seen.update(p=prompt) or 0
    )
    cli.main(["autonomy", "esp32", "--open-loop"])
    assert seen["p"] == "follow me"


def test_autonomy_requires_open_loop_until_m10(monkeypatch) -> None:
    _ctx(monkeypatch)
    # closed-loop actuation is gated to M10; without --open-loop this is a usage error.
    assert cli.main(["autonomy", "esp32"]) == 2
