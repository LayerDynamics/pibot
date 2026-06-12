"""T6.2 — the CI workflow runs the quality gate + firmware compile, and isolates hardware.

We can't run GitHub Actions here, so this validates the workflow's *structure*: it parses
as YAML, runs ``scripts/check.sh`` (the same gate as local), has a firmware-compile job,
and never sets ``PIBOT_TEST_HOST`` (so the ``@pytest.mark.hardware`` E2E stays manual-only
and skips in CI).
"""

from __future__ import annotations

from pathlib import Path

import yaml

CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_exists_and_is_valid_yaml() -> None:
    assert CI.is_file(), "missing .github/workflows/ci.yml"
    doc = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert isinstance(doc, dict) and "jobs" in doc


def test_ci_triggers_on_push_and_pull_request() -> None:
    text = CI.read_text(encoding="utf-8")
    # NB: PyYAML parses the bare ``on:`` key as boolean True, so assert on the text.
    assert "push:" in text and "pull_request:" in text


def test_ci_runs_the_same_quality_gate_as_local() -> None:
    assert "scripts/check.sh" in CI.read_text(encoding="utf-8")


def test_ci_has_a_firmware_compile_job() -> None:
    doc = yaml.safe_load(CI.read_text(encoding="utf-8"))
    blob = str(doc["jobs"]).lower()
    assert "arduino-cli" in blob and "compile" in blob


def test_ci_keeps_hardware_tests_manual_only() -> None:
    text = CI.read_text(encoding="utf-8")
    # Never point CI at a real Pi — hardware-marked tests must skip in CI.
    assert "PIBOT_TEST_HOST" not in text


def test_hardware_marker_is_registered() -> None:
    pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text("utf-8")
    assert "hardware:" in pyproject  # the marker is declared so -m 'not hardware' is valid
