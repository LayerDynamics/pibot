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


def test_ci_has_a_desktop_app_job() -> None:
    """The desktop app (SPEC-3/M12) has a CI job running the frontend + Rust gates."""
    doc = yaml.safe_load(CI.read_text(encoding="utf-8"))
    blob = str(doc["jobs"]).lower()
    assert "pnpm" in blob, "no pnpm (frontend) gate in CI"
    assert "pnpm typecheck" in blob or "typecheck" in blob
    assert "clippy" in blob, "no cargo clippy (Rust) gate in CI"


def test_ci_keeps_hardware_tests_manual_only() -> None:
    text = CI.read_text(encoding="utf-8")
    # Never point CI at a real Pi — hardware-marked tests must skip in CI.
    assert "PIBOT_TEST_HOST" not in text


def test_hardware_marker_is_registered() -> None:
    pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text("utf-8")
    assert "hardware:" in pyproject  # the marker is declared so -m 'not hardware' is valid


def test_e2e_suite_is_host_marked() -> None:
    """T12.5.7 — the macOS E2E suite is documented as host-marked (not automated in CI).

    Per CLAUDE.md's E2E definition, a real E2E test exercises the full stack with no
    mocked components — that requires a built .app and a hardware stand.  CI cannot
    provide those, so the suite is explicitly host-marked.  This test verifies the
    README exists and documents that status.
    """
    readme = Path(__file__).resolve().parent.parent / "app" / "e2e" / "README.md"
    assert readme.is_file(), "app/e2e/README.md must exist (T12.5.7)"
    text = readme.read_text(encoding="utf-8")
    assert "host-marked" in text.lower(), "E2E README must state host-marked status"
    assert "manual" in text.lower(), "E2E README must state tests are manual"
    # Verify all 5 flows are documented.
    for flow in ("connect", "teleop", "estop", "autonomy", "provisioning"):
        assert flow in text, f"E2E README missing flow: {flow}"
