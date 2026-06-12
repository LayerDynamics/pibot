# Plan — M6: Hardening

| | |
|---|---|
| **Spec** | [SPEC-1](../specs/SPEC-1-pibot-control-suite.md) §4.2 NFRs, §10–12 |
| **Milestone** | M6 |
| **Depends on** | M5 |
| **Branch** | `m6-hardening` |
| **Date** | 2026-06-11 |
| **Status** | ✅ Shipped (commit `1f6fc56`) |

> Conventions per the
> [roadmap](2026-06-11-pibot-control-suite-roadmap.md#shared-conventions-apply-to-every-task-in-every-milestone).

## Goal
Turn the feature-complete suite into something trustworthy to operate: a green test
pyramid (unit → integration → HIL → E2E), runbooks for every destructive/ recovery
path, a security pass, consistent observability, and user-facing docs.

## In scope
Cross-cutting test completion, CI wiring, runbooks, security/audit pass, logging/
`--json` consistency audit, README/usage docs, recovery-path tests.

## Out of scope
New features (the suite is complete at M5).

## Tasks

### T6.1 — Test pyramid completion + coverage gate
- **Files:** `tests/**`, `pyproject.toml` (coverage config)
- **Test first (audit-as-tests):** add the missing tests surfaced by a coverage report
  until logic modules (codec, config, inventory, devices/guards, safety, telemetry
  parsers, deploy) meet **≥ 80 %** (target the dangerous modules at ~100 %).
- **Implement:** fill gaps; delete dead branches (no stubs).
- **Done when:** `pytest --cov` meets the gate; report committed to the PR notes.

### T6.2 — CI with the echo-firmware stand
- **Files:** `.github/workflows/ci.yml` (or chosen CI), `scripts/check.sh`
- **Test first:** CI runs `scripts/check.sh` (ruff, format, mypy, pytest) on push; a
  separate job runs `arduino-cli compile` for the AVR sketch + ESP32 bridge and the
  **host-side echo-stand round-trip** (no hardware) so the control path is exercised in
  CI.
- **Implement:** CI config; mark `@pytest.mark.hardware` E2E as manual-only.
- **Done when:** CI green on a clean checkout; hardware tests clearly separated.

### T6.3 — Runbooks
- **Files:** `docs/runbooks/flash.md`, `eeprom-recovery.md`, `e-stop.md`,
  `first-boot.md`, `wireless-bringup.md`
- **Test first:** each runbook ends with a **verification step** that maps to an actual
  command/test; a doc-lint check asserts code blocks are language-tagged and links
  resolve.
- **Implement:** write the runbooks from the real commands the suite issues (incl. the
  Pi-5 power-button-hold flash entry and EEPROM recovery via SD/USB).
- **Done when:** runbooks complete; doc-lint green.

### T6.4 — Recovery-path tests for every destructive op
- **Files:** `tests/recovery/test_recovery_paths.py`
- **Test first:** for each destructive op (flash, `provision restore`, `eeprom` write,
  `deploy --rollback`) assert the documented recovery exists and is exercised (e.g.
  rollback restores prior release; clone→restore round-trips a tiny image; EEPROM
  config preserved on `-f`).
- **Implement:** any missing recovery glue.
- **Done when:** every destructive op has a passing recovery test.

### T6.5 — Security & secrets audit
- **Files:** audit notes + fixes across the tree
- **Test first:** `tests/test_security_invariants.py` — token/key files written `0600`;
  `.gitignore` excludes tokens/keys/inventory (assert none are tracked); agent refuses
  non-loopback without token; wrong-disk guard refuses system disk; secure-boot warning
  emitted when signing.
- **Implement:** fix anything the invariants catch; optionally run `/lore:audit` /
  `/lore:security-check-scan` and resolve findings.
- **Done when:** invariant tests green; no secrets tracked by git.

### T6.6 — Observability & `--json`/`--dry-run` consistency audit
- **Files:** across CLI
- **Test first:** `tests/test_cli_consistency.py` — every **read** command supports
  `--json`; every **state-changing** command supports `--dry-run`; every command
  supports `--log-json`/`--verbose`; non-zero exit codes are consistent and documented.
- **Implement:** close any gaps.
- **Done when:** consistency tests green.

### T6.7 — User docs
- **Files:** `README.md` (rewrite from stub), `docs/usage.md`, per-command help polish
- **Test first:** a help-snapshot test asserts every subcommand has a non-empty
  description and examples; README links resolve.
- **Implement:** README (what PiBot is + quickstart: discover→connect→teleop→flash),
  usage guide, polished `--help`.
- **Done when:** help-snapshot + link tests green; README reflects the shipped suite.

### T6.8 — Final hardware E2E sign-off
- **Files:** `tests/e2e/` (existing, run on hardware)
- **Test:** run the full E2E set on the real robot: discover → connect → deploy →
  teleop (wired + ≥1 wireless) with drop-to-stop → monitor real telemetry → reflash
  NVMe over USB-C and boot the new image. Record results.
- **Done when:** E2E green on hardware; results recorded in the PR notes.

## Milestone acceptance criteria (SPEC-1 §8 M6, §12)
- E2E suite green on hardware; CI green via the echo-firmware stand.
- Every destructive op has a tested recovery path.
- `--json` everywhere it should be; structured logging consistent.
- All gates green; no secrets tracked.

## Risks
- **"Done" claimed without hardware E2E** → T6.8 is explicit and required; CI stand is
  labeled an aid, not an E2E substitute (repo E2E rule).
- **Coverage gaming** → target dangerous modules near 100 %; review the report, not just
  the number.

## Definition of done
All gates pass; full E2E green on hardware; runbooks + recovery tests complete; security
invariants hold; docs reflect reality; branch ready to commit (ask first).
