# Plan — M12.5: Provisioning/Deploy + Hardening + V1 Release

> **For Claude:** REQUIRED SUB-SKILL: use `lore:execute` to implement this plan task-by-task.
> **Scope guard:** Do ONLY what is listed here. Note adjacent issues as TODOs; do NOT fix them.

**Goal:** Wrap the destructive flash/deploy/firmware/eeprom ops in the GUI behind unbypassable guards, harden security + E2E, then pass the single V1 release gate.
**Architecture:** A sidecar ops-job runner wraps the existing `pibot` ops as cancellable jobs with streamed logs; every destructive op reproduces SPEC-1's `--dry-run` → modal `--confirm` → wrong-disk guard (reusing `pibot/provision/devices.py`), enforced in the runner (not the UI). The macOS E2E harness drives the real WKWebView via an embedded-WebDriver plugin against a real sidecar + real `pibotd`.
**Tech Stack:** aiohttp (sidecar), the existing `pibot/{deploy,provision,firmware}` modules, React/Zustand + Radix `AlertDialog`, a macOS embedded-WebDriver plugin (`tauri-plugin-webdriver`/`tauri-webdriver-automation`).
**Practices:** TDD + typed-first + contract-first.
**Required skills:** none.

| | |
|---|---|
| **Spec** | [SPEC-3](../specs/SPEC-3-pibot-mission-control.md) FR-18, FR-19, FR-22, FR-25/FR-26; §3.7, §4.2 (E2E), §4.4; §5 M12.5; §6 |
| **Phase** | P5 (provisioning + release) |
| **Depends on** | M12.4 (all other domains complete) |
| **Branch** | `m12-5-provisioning-hardening-release` |
| **Date** | 2026-06-12 |
| **Status** | Not started |

## In scope
The ops-job runner + endpoints; the Provisioning screen with dry-run preview + modal confirm +
wrong-disk guard + streamed logs; the destructive-guard regression; the security-invariants
extension; native notifications; the macOS embedded-WebDriver **E2E** suite; the mission-control
runbook + README update; the **V1 release gate** + sign-off.

## Out of scope
New robot capabilities; remote policy hosts (OQ-9); WebRTC video (FR-23); any non-macOS build.

## Prerequisites
- M12.1–M12.4 done (all other domains functional).
- The existing ops live: `pibot/deploy/{service,sync}.py`, `pibot/provision/{flash,clone,eeprom,firmware,devices}.py`; the wrong-disk guard in `pibot/provision/devices.py`; `--confirm`/`--dry-run` in `pibot/cli.py`.
- The M6 secrets test: `tests/test_security_invariants.py`. The doc-lint `RUNBOOKS` list: `tests/test_docs.py:18`.

## Contracts (define first — contract-first)
```python
# pibot/mc/ops.py — typed-first job state machine.
from dataclasses import dataclass, field
@dataclass
class OpsJob:
    id: str; kind: str                  # "flash"|"clone"|"restore"|"firmware"|"eeprom"|"deploy"
    args: dict; dry_run: bool
    confirmed: bool = False             # destructive ops REQUIRE confirmed=True before exec
    guard_passed: bool = False          # wrong-disk guard (pibot/provision/devices.py)
    status: str = "queued"              # queued|preview|awaiting-confirm|running|done|error|cancelled
    progress: float = 0.0; log: list[str] = field(default_factory=list)
DESTRUCTIVE = {"flash", "clone", "restore", "eeprom"}   # must pass confirm + guard
```

## Tasks

### T12.5.1 — Ops-job runner (cancellable jobs + streamed log + guards)
- **Files:** create `pibot/mc/ops.py`; test `tests/test_mc_ops.py`.
- **Step 1 — failing test:** a job advances `queued→preview→awaiting-confirm→running→done`; a **destructive** kind (`flash`/`clone`/`restore`/`eeprom`) **refuses to run** unless `confirmed=True` **and** `guard_passed=True` (the wrong-disk guard from `pibot/provision/devices.py`) — assert it raises/stays `awaiting-confirm` otherwise; a non-destructive `deploy` runs after `preview`; cancelling a running job stops it; the log is streamed line-by-line.
- **Step 2 — run:** `pytest tests/test_mc_ops.py` → Expected: FAIL.
- **Step 3 — implement:** `OpsRunner` delegating to the existing ops functions (build the dry-run preview by calling them with `dry_run=True`; run with the real flags only after confirm + guard); the wrong-disk guard reused from `pibot/provision/devices.py` (do not re-implement it).
- **Step 4 — run:** `pytest tests/test_mc_ops.py && mypy pibot/mc` → Expected: PASS.
- **Done when:** green; the guard gating is enforced in the runner.

### T12.5.2 — Ops endpoints (`/api/ops/{kind}` + status + log WS)
- **Files:** create `pibot/mc/routes_ops.py`; modify `pibot/mc/app.py`; test `tests/test_mc_ops_routes.py`.
- **Step 1 — failing test:** `POST /api/ops/flash{args,dry_run:true}` returns `{job_id}` + the **preview**; a follow-up confirm runs it and `WS /api/ops/{id}/log` streams the log; `GET /api/ops/{id}` reports status/progress; an unknown `kind` is rejected; a destructive op without confirm never reaches `running`.
- **Step 2 — run:** `pytest tests/test_mc_ops_routes.py` → Expected: FAIL.
- **Step 3 — implement:** the routes over `OpsRunner` + a per-job log WS.
- **Step 4 — run:** `pytest tests/test_mc_ops_routes.py` → Expected: PASS.
- **Done when:** green.

### T12.5.3 — Provisioning screen (dry-run preview + modal confirm + wrong-disk guard + log)
- **Files:** create `app/src/screens/Provisioning.tsx`, `app/src/stores/opsStore.ts`, `app/src/components/{OpPreview,ConfirmModal,OpLog}.tsx`; tests `app/src/stores/opsStore.test.ts`, `app/src/components/ConfirmModal.test.tsx`.
- **Step 1 — failing test:** a destructive op **cannot dispatch execution** until the Radix `AlertDialog` confirm is satisfied **and** the wrong-disk warning is acknowledged (the button is disabled/blocked otherwise — assert no `confirm` POST fires); the dry-run preview renders before confirm; the log streams.
- **Step 2 — run:** `pnpm test` → Expected: FAIL.
- **Step 3 — implement:** the screen + `opsStore` + the `ConfirmModal` (reproduces `--confirm` + the wrong-disk guard text from the preview) + the streamed `OpLog`.
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** vitest green; the UI cannot bypass the guard.

### T12.5.4 — Destructive-guard regression (release-blocking)
- **Files:** create `tests/test_mc_destructive_guard.py`.
- **Step 1 — failing test:** for every destructive kind, assert there is **no path** through `routes_ops` + `OpsRunner` that executes the real op without `confirmed=True` **and** `guard_passed=True`; a planted "force" arg cannot skip the guard; assert **0** executions under a fuzz of payloads missing confirm/guard.
- **Step 2 — run:** `pytest tests/test_mc_destructive_guard.py` → Expected: FAIL (until fully gated).
- **Step 3 — implement:** close any gap the test finds; otherwise add only the guard test.
- **Step 4 — run:** `pytest tests/test_mc_destructive_guard.py` → Expected: PASS.
- **Done when:** green and in the default suite — release-blocking.

### T12.5.5 — Security-invariants extension + CSP/allowlist
- **Files:** modify `tests/test_security_invariants.py` (scan `pibot/mc` + `app/` config), `app/src-tauri/tauri.conf.json` (strict CSP + scoped capability allowlist); test inline.
- **Step 1 — failing test:** the invariant test scans the new surfaces (`pibot/mc`, `app/src-tauri`, `app/src`) and **fails on a planted secret** (WiFi/Nebula/`HF_TOKEN`/agent token/per-launch token); asserts the per-launch token is never written to a tracked file; asserts `tauri.conf.json` has a non-`*` CSP and a scoped allowlist (no blanket `shell`/`fs` access).
- **Step 2 — run:** `pytest tests/test_security_invariants.py` → Expected: FAIL.
- **Step 3 — implement:** extend the scan globs; lock down the CSP + allowlist to only what the app uses.
- **Step 4 — run:** `pytest tests/test_security_invariants.py` → Expected: PASS.
- **Done when:** green; the planted-secret case fails the build.

### T12.5.6 — Native notifications (FR-22)
- **Files:** create `app/src/lib/notify.ts`, `app/src/stores/notifyStore.ts`; modify `app/src/App.tsx`; test `app/src/lib/notify.test.ts`.
- **Step 1 — failing test:** the notifier fires on hot SoC / low battery / e-stop latched / stale policy **only when the window is unfocused**, and not when focused; debounced so one breach doesn't spam.
- **Step 2 — run:** `pnpm test` → Expected: FAIL.
- **Step 3 — implement:** the notifier over the alerts stream (reuse `app/src/lib/alerts.ts`) + the Tauri notification plugin; focus-gated + debounced.
- **Step 4 — run:** `pnpm typecheck && pnpm test` → Expected: PASS.
- **Done when:** vitest green.

### T12.5.7 — macOS embedded-WebDriver E2E suite (OQ-11)
- **Files:** create `app/e2e/` (harness config), `app/e2e/{connect,teleop,estop,autonomy,provisioning}.e2e.ts`; modify `app/src-tauri` (add the embedded-WebDriver plugin, **debug build only**); modify `tests/test_ci_workflow.py` (record the E2E job + its host-marked nature).
- **Step 1 — failing test (the E2E suite itself):** driving the **built debug `.app`** (real WKWebView + Rust core + bundled sidecar) against a **real `pibotd`** on the responder/Arduino-echo stand: (a) connect → telemetry values + a video frame render; (b) teleop drive → ACK observed in the DOM; (c) e-stop latches and is visually unmistakable, **including the sidecar-killed failsafe path**; (d) autonomy start→stop with a fake policy; (e) a destructive op is **blocked without the modal confirm** and **executes against a sandbox image/disk** with it. No layer mocked beyond the documented hardware stand-in.
- **Step 2 — run:** `pnpm e2e` → Expected: FAIL (no harness yet).
- **Step 3 — implement:** select + wire the embedded-WebDriver plugin (resolves OQ-11); author the five flows. **If no robust macOS mechanism stands up, honestly downgrade these to host-marked manual E2E** (documented in the suite README) — never relabel a Chromium/integration test as E2E (CLAUDE.md E2E rule, SPEC-3 §4.2).
- **Step 4 — run:** `pnpm e2e` → Expected: PASS on macOS (or recorded as manual host-marked with the gap stated).
- **Done when:** the E2E suite is green on macOS, or honestly documented as manual with the reason.

### T12.5.8 — Mission-control runbook + docs
- **Files:** create `docs/runbooks/mission-control.md`; modify `tests/test_docs.py` (add `"mission-control.md"` to `RUNBOOKS`), `README.md` (add the app + link SPEC-3).
- **Step 1 — failing test:** `tests/test_docs.py` parametrizes over the new runbook — it must exist, end with a `## Verify` step containing a real command, use language-tagged fences, and have resolving links.
- **Step 2 — run:** `pytest tests/test_docs.py` → Expected: FAIL.
- **Step 3 — implement:** write `mission-control.md` (install/launch the app, sidecar supervision, connect, policy-server management, GUI flash/deploy with the confirm + wrong-disk guards) with a `## Verify` mapping to real steps; update the README.
- **Step 4 — run:** `pytest tests/test_docs.py` → Expected: PASS.
- **Done when:** doc-lint green over the new runbook.

### T12.5.9 — V1 release gate + sign-off
- **Files:** create `docs/mission-control-v1-signoff.md` (procedure + results table, SPEC-1/2 honesty precedent).
- **Procedure:** run the full suite (`bash scripts/check.sh` + `pnpm lint/typecheck/test` + `cargo` gate + `pnpm e2e`); confirm the release-blocking regressions pass (safety-bypass, e-stop-under-loss, destructive-guard, secrets-invariant); **measure the §2.2 performance targets on the M4 Max** (teleop p95 ≤ 100 ms; video ≥ 10 fps / ≤ 400 ms; e-stop dispatch ≤ 50 ms; cold start ≤ 5 s; ≤ 1 % metrics loss) and record each; confirm all four domains functional; docs/runbook done.
- **Done when:** the sign-off table is filled (or PENDING with the gap stated for any hardware-dependent measurement); **then V1 releases**; branch `m12-5-provisioning-hardening-release` ready to commit (ask first).

## Milestone acceptance criteria (SPEC-3 M12.5 / V1)
Every destructive op requires (and cannot bypass) its dry-run+confirm+wrong-disk guard
(test-proven); the macOS E2E suite is green (or honestly manual); the security-invariants test
covers the new surfaces; performance targets are measured and recorded; all four domains
functional → **V1 ships**.

## Risks
- **Guard bypass** (R-4, Critical) → enforced in the runner not the UI; T12.5.1 + T12.5.4 are release-blocking.
- **macOS automated E2E may not stand up** (R-6 / OQ-11) → embedded-WebDriver plugin; honest manual downgrade rather than a mislabeled integration test (CLAUDE.md rule).
- **Token/loopback exposure** (R-5) → CSP + scoped allowlist + the secrets-invariant scan in T12.5.5.
- **Overclaiming the release** → the sign-off records PENDING for any unmeasured hardware target (SPEC-1/2 precedent), never a blanket "100% complete".

## Definition of done
All gates + the four release-blocking regressions green; E2E green (or documented manual);
performance recorded; runbook + README done; V1 sign-off filled; branch ready to commit (ask
first). **SPEC-3 V1 complete.**
