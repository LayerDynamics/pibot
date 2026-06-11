# Plan — M0: Foundation

| | |
|---|---|
| **Spec** | [SPEC-1](../specs/SPEC-1-pibot-control-suite.md) §4.1 FR-1, §6.1–6.2, §13 |
| **Milestone** | M0 |
| **Depends on** | — |
| **Branch** | `m0-foundation` |
| **Date** | 2026-06-11 |
| **Status** | Not started |

> Conventions (strict TDD, quality gates, git, bug rule) are defined in the
> [roadmap](2026-06-11-pibot-control-suite-roadmap.md#shared-conventions-apply-to-every-task-in-every-milestone)
> and apply to every task below.

## Goal
Stand up the project skeleton: a real git repo, the full quality-gate toolchain, the
`pibot` CLI dispatch, configuration + host inventory, and `pibot discover` backed by
the existing `tools/pifinder.py` — without breaking pifinder's standalone use.

## In scope
- git repo + `.gitignore` + Python packaging/tooling config
- `pibot/` package, `cli.py` dispatch, global flags, logging
- `config.py`, `inventory.py`, target resolution
- `discovery.py` wrapping `tools/pifinder.py`
- `pibot discover` and `pibot inventory` commands

## Out of scope
SSH ops (M1), anything touching the Pi or hardware.

## Prerequisites
- Host has `python3.14`, `pytest`, `ruff`, `black` (verified). `mypy` is **not**
  installed — T0.1 adds it to a dev venv.

## Tasks

### T0.1 — Repo + dev environment
- **Files:** `.gitignore`, `pyproject.toml`, `requirements-dev.txt`, `scripts/check.sh`,
  `pibot/__init__.py`, `tests/__init__.py`, `tests/conftest.py`
- **Test first:** `tests/test_smoke.py::test_package_imports` (import `pibot`) and
  `::test_check_script_exists` (assert `scripts/check.sh` is executable). Run → fail.
- **Implement:** `git init`; `.gitignore` covering `__pycache__/`, `*.pyc`, `.venv/`,
  `~/.config/pibot` artifacts, `*.token`, `*_ed25519*`, `dist/`, `.mypy_cache/`,
  `.ruff_cache/`, `.pytest_cache/`, `htmlcov/`. Create dev venv; install
  `ruff black mypy pytest pytest-cov`. Write `pyproject.toml` with `[tool.ruff]`,
  `[tool.ruff.format]`, `[tool.mypy]` (warn-unused, disallow-untyped-defs on
  `pibot`/`agent`), `[tool.pytest.ini_options]`, `[tool.coverage]`. `scripts/check.sh`
  runs ruff check, ruff format --check, mypy, pytest --cov in sequence and fails on
  any non-zero.
- **Done when:** `bash scripts/check.sh` runs green on the empty skeleton; smoke tests pass.

### T0.2 — Logging & global flag plumbing
- **Files:** `pibot/logging.py`, `pibot/errors.py`
- **Test first:** `tests/test_logging.py` — human vs `--log-json` formatting; level from
  `--verbose`; `PibotError` subclasses carry exit codes.
- **Implement:** structured logger (text + JSON), a typed error hierarchy mapping to
  process exit codes.
- **Done when:** tests assert both formats and exit-code mapping.

### T0.3 — Configuration
- **Files:** `pibot/config.py`
- **Test first:** `tests/test_config.py` — defaults when no file; user override merge;
  malformed TOML → `PibotError` with clear message; unknown keys rejected.
- **Implement:** load `~/.config/pibot/config.toml` (path overridable via env for
  tests) into a typed dataclass: default user/identity, transport defaults, teleop
  rate, watchdog ms, thresholds, agent bind/token path. Sensible hard defaults.
- **Done when:** all config tests green; 100 % branch coverage on the loader.

### T0.4 — Inventory & target resolution
- **Files:** `pibot/inventory.py`
- **Test first:** `tests/test_inventory.py` — add/rm/alias/list round-trip to TOML;
  duplicate alias handling; resolution order **alias → inventory IP → `.local` →
  raw IP**; unknown target error.
- **Implement:** `Inventory` (load/save `~/.config/pibot/inventory.toml`), records
  `{alias, ip, mac, vendor, hostname, user, link, last_seen}`, and `resolve(target)`.
- **Done when:** resolution tests cover every branch incl. malformed records.

### T0.5 — Discovery backend (wrap pifinder, keep standalone)
- **Files:** `pibot/discovery.py`; minimal shim so `tools/pifinder.py` is importable
  without moving it (add a thin `pibot/_pifinder.py` loader or package-path insert).
- **Test first:** `tests/test_discovery.py` — `discover()` returns the same host
  objects pifinder produces (monkeypatch pifinder's `discover` with a fake to assert
  delegation + JSON shape parity); `tools/pifinder.py --self-test` still passes
  (subprocess assertion).
- **Implement:** `discovery.discover(...)` imports and calls `pifinder.discover`,
  adapts results into the inventory record shape, optionally upserts last-seen.
- **Done when:** delegation + shape tests green; **`python3 tools/pifinder.py
  --self-test` still exits 0** (regression guard — do not break the shipped tool).

### T0.6 — CLI dispatch: `discover`, `inventory`
- **Files:** `pibot/cli.py`, `pibot/__main__.py`, `pyproject.toml` console-script
  entry `pibot = "pibot.cli:main"`
- **Test first:** `tests/test_cli.py` — `pibot --help` exit 0; unknown command exit 2;
  global flags parsed (`--json/--verbose/--log-json/--timeout`); `pibot discover
  --json` emits valid JSON (discovery monkeypatched); `pibot inventory add/list`
  mutate and read the store.
- **Implement:** argparse dispatcher with subcommands `discover` and `inventory`
  (`list|add|rm|alias`), wired to T0.3–T0.5.
- **Done when:** CLI tests green; `pibot discover --json` parity with `pifinder.py
  --json` confirmed by a test comparing keys.

## Milestone acceptance criteria (SPEC-1 §8 M0)
- `pibot discover --json` returns the same data as `pifinder.py`.
- `pibot inventory add` persists; unit tests for config/inventory pass.
- `tools/pifinder.py` standalone + `--self-test` unaffected.
- `scripts/check.sh` (all four gates) green.

## Risks
- **Breaking pifinder while wrapping it** → mitigated by the standalone regression
  guard in T0.5 (subprocess `--self-test`).
- **mypy strictness churn** → start strict on `pibot`/`agent` only; pifinder.py kept
  out of `disallow-untyped-defs` scope initially (it already has hints; tighten in M6).

## Definition of done
All tasks' gates pass; milestone acceptance met; branch `m0-foundation` ready to
commit (ask user first).
