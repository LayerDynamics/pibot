# Plan — M1: Connection & SSH Ops

| | |
|---|---|
| **Spec** | [SPEC-1](../specs/SPEC-1-pibot-control-suite.md) §4.1 FR-2 |
| **Milestone** | M1 |
| **Depends on** | M0 |
| **Branch** | `m1-connection-ssh-ops` |
| **Date** | 2026-06-11 |
| **Status** | ✅ Shipped (commit `08d9cd2`) |

> Conventions (strict TDD, quality gates, git, bug rule) per the
> [roadmap](2026-06-11-pibot-control-suite-roadmap.md#shared-conventions-apply-to-every-task-in-every-milestone).

## Goal
Make the robot operable over SSH from the Mac: run remote commands, transfer files,
provision keys, open shells and tunnels — all idempotent, scriptable (`--json`), and
with the correct default user resolved from the Pi's SSH banner.

## In scope
`connect`, `run`, `push`, `pull`, `keys install`, `tunnel`; SSH command-construction
layer; banner-derived user resolution.

## Out of scope
Flashing/provisioning (M2), agent/control (M3+).

## Prerequisites
- M0 complete (CLI, config, inventory, target resolution).
- A reachable Pi for integration tests (`pibot.local` / last seen `192.168.1.99`).

## Design note
SSH/SCP/RSYNC are driven via the **system binaries through subprocess** (rsync is the
right tool for M5 deploy; reusing it here keeps one transfer path). `paramiko` is an
optional pure-Python fallback only if a system `ssh` is unavailable. All
command-construction is a pure function → fully unit-testable without a network.

## Tasks

### T1.1 — SSH command builder (pure, fully TDD)
- **Files:** `pibot/connection/sshcmd.py`
- **Test first:** `tests/test_sshcmd.py` — argv construction for run/shell/scp/rsync/
  tunnel given user, identity, host, options (BatchMode, StrictHostKeyChecking accept-new,
  ConnectTimeout); special-char escaping; identity omitted when None.
- **Implement:** pure builders returning argv lists (no execution).
- **Done when:** exhaustive argv tests green (this is the safety-critical surface).

### T1.2 — Runner + user resolution
- **Files:** `pibot/connection/runner.py`, `pibot/connection/user.py`
- **Test first:** `tests/test_runner.py` (fake subprocess: stdout/stderr/exit-code
  propagation, timeout → `PibotError`); `tests/test_user.py` (banner `…Ubuntu…` → `ubuntu`,
  `…Raspbian…`/`…Debian…`+Pi → `pi`, else config default — reuse pifinder banner logic).
- **Implement:** subprocess runner (stream or capture) and `resolve_user(target, cfg)`
  that probes the SSH banner via `pifinder`/`socket` and applies the precedence
  explicit `--user` → banner → config default.
- **Done when:** runner + resolution branches covered.

### T1.3 — `pibot run` and `pibot connect`
- **Files:** `pibot/connection/commands.py`, CLI wiring in `pibot/cli.py`
- **Test first:** `tests/test_cmd_run.py` — `pibot run t -- uptime` builds correct argv,
  streams, returns exit code; `--json` wraps `{host,user,cmd,exit,stdout,stderr,duration}`.
  `pibot connect` execs an interactive ssh (assert argv; no capture).
- **Implement:** `run` (capture+`--json` or stream) and `connect` (exec ssh, inherit tty).
- **Done when:** unit tests green.

### T1.4 — `pibot push` / `pibot pull`
- **Files:** `pibot/connection/transfer.py`
- **Test first:** `tests/test_transfer.py` — rsync argv (archive, compress, `--info`,
  delete only when asked); scp fallback when rsync absent; post-transfer checksum
  verification logic (compare local vs remote `sha256` from a fake runner).
- **Implement:** rsync-first with scp fallback; optional `--verify` runs remote
  `sha256sum` and compares.
- **Done when:** unit tests green incl. fallback + verify branches.

### T1.5 — `pibot keys install` (idempotent)
- **Files:** `pibot/connection/keys.py`
- **Test first:** `tests/test_keys.py` — generates `~/.ssh/pibot_ed25519` only if
  absent; building the remote append command is idempotent (uses
  `ssh-copy-id`-style guarded append so re-runs don't duplicate the key); records the
  identity into config.
- **Implement:** ed25519 keygen (via `ssh-keygen`), guarded remote
  `authorized_keys` append, config update.
- **Done when:** idempotency + keygen-skip tests green.

### T1.6 — `pibot tunnel`
- **Files:** `pibot/connection/tunnel.py`
- **Test first:** `tests/test_tunnel.py` — parse `L:host:R`, build `ssh -N -L` argv;
  reject malformed spec.
- **Implement:** local-forward tunnel (foreground, `-N`), used later to reach `pibotd`.
- **Done when:** parse + argv tests green.

### T1.7 — Integration suite (real Pi, opt-in)
- **Files:** `tests/integration/test_ssh_live.py` (marked `@pytest.mark.hardware`,
  skipped unless `PIBOT_TEST_HOST` is set)
- **Test:** after `keys install`, `pibot run $HOST -- uptime` exits 0 passwordlessly;
  `push`→`pull` round-trip of a temp file verifies identical sha256; `tunnel` opens
  and a probe connects.
- **Done when:** suite passes against the real Pi when `PIBOT_TEST_HOST` is set; cleanly
  skips in CI.

## Milestone acceptance criteria (SPEC-1 §8 M1)
- Passwordless `pibot run <pi> -- uptime` works after `keys install` (real Pi).
- File round-trips verified by checksum.
- All gates green; unit tests cover command construction without a network.

## Risks
- **Host-key prompts blocking automation** → `StrictHostKeyChecking=accept-new` +
  `BatchMode=yes`; surfaced in `sshcmd` tests.
- **Wrong default user** → banner resolution reuses pifinder's already-tested logic;
  explicit `--user` always wins.

## Definition of done
All gates pass; acceptance met; integration suite green against the real Pi; branch
ready to commit (ask first).
