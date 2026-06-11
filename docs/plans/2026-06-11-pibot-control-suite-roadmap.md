# Plan Roadmap — PiBot Control Suite

| | |
|---|---|
| **Source spec** | [SPEC-1 — PiBot Control Suite](../specs/SPEC-1-pibot-control-suite.md) |
| **Created** | 2026-06-11 |
| **Plan set** | One file per milestone, M0 → M6 |
| **Status** | Not started |

This roadmap indexes the seven milestone plans. Each milestone file is
self-contained and executable on its own (via `/lore:continue` or `/lore:execute`),
but they share the conventions below — **read this once, then the per-milestone file.**

## Milestone index

| # | Plan file | Delivers | Depends on |
|---|---|---|---|
| M0 | [m0-foundation](2026-06-11-m0-foundation.md) | git + tooling + `pibot` CLI skeleton + config/inventory + `discover` | — |
| M1 | [m1-connection-ssh-ops](2026-06-11-m1-connection-ssh-ops.md) | `connect`/`run`/`push`/`pull`/`keys`/`tunnel` | M0 |
| M2 | [m2-provisioning-flashing](2026-06-11-m2-provisioning-flashing.md) | `flash`/`provision`/`eeprom`/`firmware` | M1 |
| M3 | [m3-transport-protocol-control](2026-06-11-m3-transport-protocol-control.md) | protocol codec + `Transport` (serial **+ TCP**) + `cmd`/`estop` + ref firmware | M1 |
| M4 | [m4-agent-teleop-telemetry](2026-06-11-m4-agent-teleop-telemetry.md) | `pibotd` agent + safety + telemetry + `teleop`/`monitor` | M3 |
| M5 | [m5-deploy-wireless-transports](2026-06-11-m5-deploy-wireless-transports.md) | `deploy` + rfcomm/ble/i2c/uart + `play` | M4 |
| M6 | [m6-hardening](2026-06-11-m6-hardening.md) | full tests, runbooks, security pass, docs | M5 |

> **Refinement vs SPEC-1 §8:** per the planning decision, the **TCP/Wi-Fi transport
> is promoted from M5 into M3** (built alongside serial), so wireless teleop is
> reachable by M4. RFCOMM/BLE/I²C/UART remain in M5. SPEC-1 DL-6/§8 are updated to
> match.

## Shared conventions (apply to every task in every milestone)

### Development discipline — strict TDD
Every task follows **red → green → refactor**:
1. Write the failing test(s) first; run them; confirm they fail for the right reason.
2. Write the minimal implementation to pass.
3. Refactor with tests green.
Hardware/I-O paths (SSH, serial, BLE, agent sockets, flashing) are tested against
**fakes, loopbacks (pty/TCP echo), and the Arduino echo stand** — never by skipping
the test. Real-hardware E2E is additive on top, not a replacement.

### Quality gates — definition of done for every task
A task is not done until **all** of these pass:
- `ruff check .` — zero lint errors
- `ruff format --check .` — formatting clean (black-compatible)
- `mypy pibot agent` — zero type errors (strict-ish; see `pyproject.toml`)
- `pytest` — all green, **coverage ≥ 80 % on logic modules** (codec, config, guards,
  safety, parsers)
- No stubs/TODO/placeholder (repo rule); `--json` on read commands; `--dry-run` on
  state-changing commands

A single script — `scripts/check.sh` — runs all gates and is the milestone gate too.

### Version control
- M0 runs `git init` + `.gitignore`.
- Each milestone is a branch: `git checkout -b m<n>-<slug>`.
- Commit at the **end** of a milestone (or at meaningful checkpoints) — **always ask
  the user before committing** (repo rule). Never `git stash`/`checkout --`/`reset
  --hard` to compare; read history instead (repo rule).

### Bug rule
Any bug found during a milestone gets a **regression test that fails before the fix
and passes after**, before the task closes (repo rule).

### Safety rule (control milestones M3–M5)
E-stop and deadman watchdog exist independently in client, agent, **and** firmware.
No wireless transport may be the sole carrier of a stop signal. Every motion test
asserts the fail-safe (drop comms → robot stops).

## Hardware & external dependencies (install gates, surfaced where needed)
- **M2** needs `rpiboot`/`usbboot` (build from source) and `rpi-imager` on the Mac —
  neither is currently installed (verified 2026-06-11). M2 T2.0 installs them.
- **M2/M3/M4/M5** real-hardware E2E needs the physical robot (Pi 5 at `pibot.local` /
  last seen `192.168.1.99`) and the Arduino subsystem. CI uses the echo stand.
- `mypy` is not installed (verified 2026-06-11); M0 adds it to the dev venv.
