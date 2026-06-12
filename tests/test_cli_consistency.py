"""T6.6 — CLI observability & flag-consistency invariants, driven off the live registry.

This test walks the *actual* subparser tree, so adding a new command without
classifying it (or without the flags its class requires) breaks the build — it is not a
hand-maintained enumeration of today's commands. The contract:

  - every leaf command is classified (read / interactive / state-changing / meta);
  - every command accepts the global ``--json`` / ``--verbose`` / ``--log-json`` flags;
  - every **state-changing** command accepts ``--dry-run`` (preview before you mutate).
"""

from __future__ import annotations

import argparse

import pytest

from pibot.cli import build_parser

# Classification of every leaf command. A new command must be added here or
# ``test_every_command_is_classified`` fails — the registry is the source of truth.
READ = {"discover", "inventory list", "monitor", "agent status", "agent logs", "agent token"}
# NB: `autonomy` is open-loop only today (streams obs + logs actions, no actuation) — an
# interactive run loop like teleop. M10 adds a closed-loop actuating mode, at which point
# it becomes state-changing and gains --dry-run (plan T10.4).
INTERACTIVE = {"run", "connect", "tunnel", "teleop", "autonomy"}
STATE_CHANGING = {
    "cmd",
    "estop",
    "push",
    "pull",
    "keys install",
    "eeprom",
    "provision clone",
    "provision restore",
    "firmware flash",
    "agent start",
    "agent stop",
    "play",
    "flash",
    "deploy",
}
# META = local-only / reversible operations deliberately exempt from --dry-run:
# inventory edits write local metadata (trivially reversible), firmware build compiles
# locally. NB: ``agent token`` is classified READ — it *shows* the token, generating a
# 0600 file once if absent (idempotent), so it is exempt too. Reclassify into
# STATE_CHANGING above if any of these should gain a --dry-run preview.
META = {"inventory add", "inventory rm", "inventory alias", "firmware build"}

ALL_CLASSIFIED = READ | INTERACTIVE | STATE_CHANGING | META


def _leaf_parsers(
    parser: argparse.ArgumentParser, prefix: str = ""
) -> dict[str, argparse.ArgumentParser]:
    """Recurse the subparser tree, returning ``{command path: leaf parser}``."""
    subactions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subactions:
        return {prefix.strip(): parser}
    leaves: dict[str, argparse.ArgumentParser] = {}
    for action in subactions:
        for name, sub in action.choices.items():
            leaves.update(_leaf_parsers(sub, f"{prefix} {name}"))
    return leaves


def _options(parser: argparse.ArgumentParser) -> set[str]:
    return {opt for action in parser._actions for opt in action.option_strings}


LEAVES = _leaf_parsers(build_parser())


def test_registry_discovered_some_commands() -> None:
    # sanity: the walker actually found the tree (guards against a silent empty pass)
    assert {"discover", "cmd", "deploy", "agent start"} <= set(LEAVES)


def test_every_command_is_classified() -> None:
    unclassified = set(LEAVES) - ALL_CLASSIFIED
    assert not unclassified, (
        f"new command(s) not classified in test_cli_consistency: {unclassified}"
    )
    stale = ALL_CLASSIFIED - set(LEAVES)
    assert not stale, f"classified command(s) no longer in the CLI: {stale}"


@pytest.mark.parametrize("name", sorted(ALL_CLASSIFIED))
def test_every_command_has_global_observability_flags(name: str) -> None:
    opts = _options(LEAVES[name])
    for flag in ("--json", "--verbose", "--log-json"):
        assert flag in opts, f"{name} is missing the global {flag} flag"


@pytest.mark.parametrize("name", sorted(STATE_CHANGING))
def test_state_changing_commands_support_dry_run(name: str) -> None:
    opts = _options(LEAVES[name])
    assert "--dry-run" in opts, f"state-changing command {name!r} must support --dry-run"


# ---- the dry-run flag actually previews and mutates nothing ---------------


class _Inv:
    def resolve(self, target: str) -> str:
        return "192.168.1.99"


def test_cmd_dry_run_prints_frame_without_opening_a_transport(capsys) -> None:
    from pibot.config import Config
    from pibot.control import oneshot

    # transport=serial would try to open /dev/ttyACM0 if dry-run leaked through.
    rc = oneshot.cmd(
        "pibot",
        "drive",
        ["0.5", "0.0"],
        cfg=Config(transport="serial"),
        inventory=_Inv(),
        dry_run=True,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out and "drive" in out


def test_eeprom_update_dry_run_skips_confirm_and_runs_nothing(capsys) -> None:
    from pibot.config import Config
    from pibot.provision import eeprom

    rc = eeprom.update("pibot", cfg=Config(), inventory=_Inv(), user="pi", dry_run=True)
    assert rc == 0  # no PibotError despite no --confirm: dry-run never mutates
    assert "rpi-eeprom-update" in capsys.readouterr().out


def test_clone_dry_run_writes_no_image(tmp_path, capsys) -> None:
    from pibot.config import Config
    from pibot.provision import clone

    out = tmp_path / "backup.img.gz"
    rc = clone.clone("pibot", str(out), cfg=Config(), inventory=_Inv(), user="pi", dry_run=True)
    assert rc == 0
    assert not out.exists()  # nothing written
    assert "dd if=/dev/nvme0n1" in capsys.readouterr().out
