# Plan — M7: Hardened Runtime & Prove-the-Pipe

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. If you discover adjacent issues, note them as a TODO and continue — do NOT fix them.

| | |
|---|---|
| **Spec** | [SPEC-2](../specs/SPEC-2-pibot-autonomy-platform.md) §3.10, §4.1 Phase A, FR-7/8 |
| **Milestone** | M7 (first SPEC-2 milestone) |
| **Depends on** | SPEC-1 M0–M6 (shipped); research report reflash recipe; Nebula overlay |
| **Branch** | `m7-runtime-and-pipe` |
| **Date** | 2026-06-11 |
| **Status** | ✅ Software shipped + committed (T7.1–T7.5; gate-green). HIL pending hardware — T7.6 (reflash + harden + prove-the-pipe). |

**Goal:** A trustworthy reflashed Pi (Bookworm + research hardening) that round-trips the openpi policy websocket to the M4 Max — the foundation autonomy runs on.
**Architecture:** Extend SPEC-1's flash/deploy with the hardened-runtime config builders; add the `pibot[ml]` optional extra carrying `openpi-client` (numpy<2.0 contained); a `simple_client` latency probe over Nebula.
**Practices:** TDD + typed-first + contract-first on software seams; ruff/format/mypy/pytest ≥80% gate per task; hardware steps are gated HIL procedures (marked `hardware`, deselected by default). Branch-per-milestone, commit at boundaries (ask first).

## Goal
Reflash the Pi to the researched baseline and prove the policy pipe end-to-end with no robot-specific code — pure feasibility + a runtime you can trust.

## In scope
The `pibot[ml]` extra + ml config fields; hardened first-boot/provision config builders (NVMe ASPM fix, overlayfs, watchdog, journald-volatile); hardened systemd unit renderers (pibotd + nebula `Restart=always`, `RuntimeWatchdogSec=14`); the `simple_client` latency probe; the reflash + power-yank HIL procedure.

## Out of scope
Camera, observations, actuation, the model itself (M8+). Fine-tuning (M10).

## Prerequisites
- Nebula overlay up (Mac↔Pi) — [nebula-overlay runbook](../runbooks/nebula-overlay.md).
- M4 Max can serve a stock π₀.₅ over websocket (PIML §6 recipe) for the latency probe.

## Tasks

### T7.1 — `pibot[ml]` optional extra + import isolation
- **Files:** `pyproject.toml` (`[project.optional-dependencies] ml = ["openpi-client", "numpy>=1.22.4,<2.0", "opencv-python-headless", ...]`); `tests/test_ml_isolation.py`
- **Test first:** importing `pibot.cli` / `agent.app` MUST NOT import `numpy`/`openpi_client` (assert modules absent from `sys.modules` after a fresh import in a subprocess) — the `numpy<2.0` pin can never destabilize the core suite (FR-8, R-4).
- **Implement:** add the `ml` extra; keep all `pibot/ml/*` imports lazy.
- **Done when:** isolation test green; `pip install -e '.[ml]'` resolves.

### T7.2 — ML config fields (typed-first)
- **Files:** `pibot/config.py` (+ `policy_host`, `policy_port=8000`, `action_horizon=50`, `control_hz=20`, `camera_device="/dev/video0"`, `prompt=""`); `tests/test_config.py`
- **Test first:** the new keys parse/validate with correct types and defaults; wrong types raise `ConfigError`.
- **Implement:** add fields + `_FIELD_TYPES` entries (mirrors existing pattern).
- **Done when:** config tests green; `pibot`’s existing config tests still pass.

### T7.3 — Hardened first-boot/runtime config builders
- **Files:** `pibot/provision/hardening.py`; `tests/test_hardening.py`
- **Test first:** builders emit the exact directives — `cmdline.txt` gains `pcie_aspm=off nvme_core.default_ps_max_latency_us=0`; `config.txt` gains `dtparam=watchdog=on`; a journald drop-in sets `Storage=volatile`; an fstab snippet mounts a small `rw` `/var/lib/pibot` + `noatime,commit=3`. Assert each token present.
- **Implement:** pure string/argv builders (no I/O), reused by flash first-boot + deploy.
- **Done when:** builder tests green (every research directive asserted).

### T7.4 — Hardened systemd unit renderers
- **Files:** `pibot/deploy/service.py` (extend `render_unit`; add `render_watchdog_conf`, `render_nebula_unit`); `tests/test_deploy_service.py`
- **Test first:** the pibotd unit gains `Type=notify`-ready fields; a `system.conf` drop-in sets `RuntimeWatchdogSec=14` (≤15 s, per research R); the nebula unit is `Restart=always` + unprivileged (`AmbientCapabilities=CAP_NET_ADMIN`).
- **Implement:** extend the M5 renderers.
- **Done when:** render tests green.

### T7.5 — `simple_client` latency probe (the pipe check)
- **Files:** `tools/pipe_check.py`; `tests/test_pipe_check.py`
- **Test first:** against a **fake websocket policy** (returns a canned chunk), `pipe_check` performs N round-trips and reports min/median/p95 latency + chunk shape; exits non-zero if unreachable. (No real network.)
- **Implement:** thin wrapper over `openpi_client.WebsocketClientPolicy` with timing; lazy ml import.
- **Done when:** probe test green; `python tools/pipe_check.py --host <ip> --port 8000` shape documented.

### T7.6 — (HIL) Reflash + harden + prove the pipe
- **Files:** `docs/runbooks/autonomy-runtime.md` (procedure + results table)
- **Procedure:** flash Pi OS Lite 64-bit via `pibot flash --os rpi-os` with key embedding → apply T7.3/T7.4 hardening → verify SSH-key login (lockout fixed) → `dmesg | grep -i nvme` clean → yank-power ×5 (rootfs intact) → install `pibot[ml]` → run `tools/pipe_check.py` against the M4 Max server over Nebula.
- **Done when:** lockout fixed; pipe round-trips; latency recorded in the runbook; 0 corruptions over the yank campaign.

## Milestone acceptance criteria (SPEC-2 M7)
SSH-key login works; `simple_client`/`pipe_check` round-trips to the M4 Max server; round-trip latency logged; a yanked-power test leaves the rootfs intact.

## Risks
- **NVMe ASPM not actually disabled** → assert the cmdline token in T7.3 + re-check `dmesg` in T7.6.
- **Nebula path flaky for the probe** → fall back to LAN IP for the latency baseline; note both.

## Definition of done
All software tasks’ gates green (ruff/format/mypy/pytest ≥80%); HIL procedure executed and recorded; branch ready to commit (ask first).
