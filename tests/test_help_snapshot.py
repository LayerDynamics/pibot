"""T6.7 — every command is self-describing: a non-empty help line + a usage example.

Walks the live subparser tree (so a new command without help fails the build) and checks
that the user guide documents every top-level command with a runnable example.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from pibot.cli import build_parser

REPO = Path(__file__).resolve().parent.parent
USAGE = REPO / "docs" / "usage.md"


def _command_helps(parser: argparse.ArgumentParser, prefix: str = "") -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            helps = {ca.dest: ca.help for ca in action._choices_actions}
            for name, sub in action.choices.items():
                path = f"{prefix} {name}".strip()
                out[path] = helps.get(name)
                out.update(_command_helps(sub, path))
    return out


HELPS = _command_helps(build_parser())
TOP_LEVEL = sorted({path.split()[0] for path in HELPS})


def test_found_the_command_tree() -> None:
    assert {"discover", "cmd", "deploy", "agent"} <= set(TOP_LEVEL)


@pytest.mark.parametrize("path", sorted(HELPS))
def test_every_command_has_a_nonempty_help_line(path: str) -> None:
    help_text = HELPS[path]
    assert help_text and help_text.strip(), f"command {path!r} has no help/description"


def test_usage_doc_exists() -> None:
    assert USAGE.is_file(), "missing docs/usage.md"


@pytest.mark.parametrize("command", sorted({p.split()[0] for p in _command_helps(build_parser())}))
def test_usage_doc_has_an_example_for_every_top_level_command(command: str) -> None:
    text = USAGE.read_text(encoding="utf-8")
    assert f"pibot {command}" in text, f"docs/usage.md has no example for `pibot {command}`"
