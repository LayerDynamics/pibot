# PiBot — Implementation Status & TODO

> What is and isn't implemented, cross-referenced from the specs (`docs/specs/SPEC-1/2/3`)
> and the milestone plans (`docs/plans/`) against the **actual working-tree code** on branch
> `m12-2-teleop-estop-video`, verified 2026-06-12.
>
> **Method:** ran all three test suites, checked existence + integration (not just existence)
> of every file named in each plan task, traced route/handler registration, and read the four
> release-blocking regression tests. Evidence + citations are inline and in the appendix.
> The plan `Status` lines are **stale and unreliable** (see §5) — this document is grounded in
> code, not in those headers.

---

## 0. Progress update — 2026-06-12 (this session)

**Category A (frontend integration) and the repo-state doc fixes are DONE and verified** —
frontend gate green (typecheck + lint clean, **123 vitest tests pass**, incl. a new nav
smoke test). Completed:

- **A1** — `App.tsx` now has a screen-navigation bar mounting all five screens
  (Dashboard / Drive / Autonomy / Data / Provisioning); `App.test.tsx` guards it.
- **A2** — the dead top-bar placeholder is replaced by the functional `EstopButton`
  (posts `/api/estop`, falls back to the Rust `estop_now`).
- **A3** — `app/src/stores/notifyStore.ts` created and wired (telemetry alerts →
  `notifyAlerts`, focus-gated + debounced) with `notifyStore.test.ts` (4 tests).
- **Repo doc fixes** — all stale plan `Status` headers corrected; the V1 sign-off
  overclaim reconciled.
- Fixed pre-existing WIP gate breakers found along the way: an unresolved notification-plugin
  import (added an ambient type shim), an unused `setArgs` in `Provisioning.tsx` (now a real
  JSON args input), and an ESLint unused-param error (added the `^_` ignore convention).

**Still open:** B (HIL), C (host-marked/manual E2E), D (release-gate perf) — all
hardware/GUI-gated. The M12.2–M12.5 work is committed (`7275e08`, full gate green). **Real
OS-notification delivery is now wired** (FR-22 fully done — see §3): the
`@tauri-apps/plugin-notification` JS package + Rust `tauri-plugin-notification` are installed,
registered, and capability-granted; `notify.ts` requests permission then delivers.

Items resolved this session are marked **✅ DONE** in the sections below.

---

## 1. Executive summary

- **SPEC-1 (Control Suite, M0–M6)** and **SPEC-2 (Autonomy Platform, M7–M11)**: software **shipped and committed**. The only open items are hardware-in-the-loop (HIL) runs + two hardware E2E sign-offs that require the physical robot.
- **SPEC-3 (Mission Control, M12.1–M12.5)**:
  - **Python sidecar (`pibot/mc`) + on-Pi agent (`agent/`): fully implemented and wired.** Every route module is registered in `pibot/mc/app.py:21-36`; 833 Python tests pass.
  - **Rust core (`app/src-tauri`): fully implemented and wired.** Supervisor, token broker, `cache_robot_endpoint`/`estop_now`, and the global e-stop hotkey are all registered (`lib.rs:59-65`, `lib.rs:108-115`); 9 Rust tests pass.
  - **React frontend (`app/src`): every screen, store, component and lib is implemented and unit-tested (123 vitest tests pass).** As of this session it is also **integrated** — `App.tsx` mounts all five screens behind a nav bar, the functional `EstopButton` is in the top bar, and `notifyStore` wires alerts → notifications (§0). *(Originally these surfaces were orphaned — imported only by their own tests — which is the gap this session closed.)*
- **The V1 sign-off (`docs/mission-control-v1-signoff.md`)** previously marked all five M12 milestones "✅ complete" while the frontend was un-integrated and perf targets pending — an overclaim. **Now reconciled** (§7): milestone rows read "software + GUI · release gate open," with the 2026-06-12 integration correction recorded in the doc.

**Bottom line:** almost all *logic* is written and tested, the frontend is wired, the SPEC-3 work is committed (`7275e08`), and native notifications now really deliver. The genuinely outstanding work is **(B) hardware-in-the-loop runs**, **(C) the 5 macOS GUI E2E flows**, and **(D) the V1 release-gate measurements** — all hardware/GUI-gated. **(A) frontend wiring and FR-22 delivery are done.**

---

## 2. What IS implemented (verified)

| Layer | Status | Evidence |
|---|---|---|
| SPEC-1 CLI + `pibotd` (M0–M6) | ✅ shipped + committed | plan statuses M0–M6 "✅ Shipped" w/ commits; in git history |
| SPEC-2 autonomy software (M7–M11) | ✅ shipped + committed | roadmap "SPEC-2 (M7–M11, done)"; git `M9/M10/M11` commits; closed-loop in-process in `agent/autonomy.py` |
| Sidecar routes (M12.2–M12.5) | ✅ implemented + registered | `pibot/mc/app.py:21-36` imports & registers autonomy, control, video, metrics, sessions, episodes, record, finetune, policy_server, ops, link, config, inventory |
| Agent camera broker + `WS /video` (M12.2) | ✅ implemented | `agent/video.py`, `agent/app.py` handler; `tests/test_camera_broker.py`, `tests/test_agent_video.py` green |
| Rust supervisor + token + e-stop failsafe (M12.1–M12.2) | ✅ implemented + wired | `app/src-tauri/src/{supervisor,token,commands,state}.rs`; `lib.rs:59-65,108-115`; `estop_now_posts_to_robot_with_bearer` cargo test green |
| Frontend (M12.2–M12.5 screens/stores/libs) | ✅ implemented + **now integrated** | all five screens mounted in `App.tsx` behind a nav bar; functional `EstopButton` + `notifyStore` wired; 123 vitest green (§0) |
| Release-blocking regressions | ✅ real & green | safety-bypass, e-stop-failsafe, destructive-guard, secrets-invariant — all assert real behavior (see appendix) |
| Runbooks + sign-off scaffolding | ✅ present | `docs/runbooks/mission-control.md`, three sign-off docs exist (honestly marked PENDING) |

---

## 3. Category A — Frontend integration ✅ DONE (this session)

The M12.2–M12.5 React building blocks were implemented + unit-tested but not mounted in the
app shell; a user saw only the Dashboard. Now wired (frontend gate green, 123 tests):

- [x] **Screen navigation + all five screens mounted.** `app/src/App.tsx` renders a nav bar
  and mounts Dashboard / Drive / Autonomy / Data / Provisioning (the latter two receive the
  resolved `McEndpoint` as their `ep` prop). A button nav (not Radix Tabs) was chosen so its
  roving arrow-key focus can't collide with Drive's arrow-key teleop. `App.test.tsx` adds a
  navigation smoke test asserting each screen's testid renders.
- [x] **Functional e-stop in the shell.** The dead `<button>` placeholder is replaced by
  `components/EstopButton.tsx`, fed `ep.url`/`ep.token`; it posts `/api/estop` and falls back
  to the Rust `estop_now` failsafe. (The `Ctrl+Shift+E` global hotkey already worked.)
- [x] **Native notifications wired (FR-22).** `app/src/stores/notifyStore.ts` created;
  `start()` subscribes the telemetry store and forwards new alert sets to `notifyAlerts`
  (focus-gated + debounced), started from an `App.tsx` effect. `notifyStore.test.ts` (4 tests)
  proves alert → notification, focus gating, the enable toggle, and the empty case.
  - [x] **Real OS delivery — ✅ DONE (this session).** Installed `@tauri-apps/plugin-notification`
    (2.3.3) + the Rust `tauri-plugin-notification` crate; registered it in `lib.rs`
    (`.plugin(tauri_plugin_notification::init())`) and granted `notification:default` in
    `capabilities/default.json`. `notify.ts` `_tauriSend` now requests the OS permission
    (`isPermissionGranted`/`requestPermission`) before `sendNotification`. The vite mock alias
    was scoped to **tests only** (`test.alias`) so the production build uses the real plugin, and
    the obsolete ambient type shim was emptied. Gate green (frontend 123, cargo fmt/clippy/test).
- [x] **Endpoint-caching path confirmed.** The Rust failsafe gets its target from the
  sidecar's `ROBOT_ENDPOINT=` stdout line (`lib.rs:92`); the JS `cache_robot_endpoint` command
  remains exposed but unused — left in place, as the stdout path is authoritative.

---

## 4. TODO — Category B: Hardware-in-the-loop (needs the physical Pi 5 + robot)

These are explicitly marked `(HIL)` in the plans and were always deferred to real hardware. Software seams for each are done and tested with fakes.

- [ ] **T7.6** — Reflash + harden the Pi + prove the policy pipe over Nebula; record latency in `docs/runbooks/autonomy-runtime.md`.
- [ ] **T8.6** — Real open-loop run (camera → observation → policy, log-only, no actuation).
- [ ] **T9.6** — Record real demonstrations + build a LeRobot dataset on hardware.
- [ ] **T10.5** — Fine-tune π₀.₅ on real data + serve the checkpoint.
- [ ] **T10.6** — Closed-loop drive on ≥1 task on the real robot.
- [ ] **T11.4** — Multi-task demos + fine-tune on hardware.
- [ ] **T6.8** — Final SPEC-1 hardware E2E sign-off: `docs/hardware-e2e-signoff.md` — all 8 steps ⬜ pending (discover → SSH → deploy → rollback → telemetry → teleop+drop-to-stop → monitor → reflash).
- [ ] **T11.6** — Full SPEC-2 autonomy E2E sign-off: `docs/autonomy-e2e-signoff.md` — all 7 steps ⬜ pending (drive-to-goal / follow / explore closed-loop, live policy-link, hardware drop-to-stop, power-loss survival, no-bypass).

---

## 5. Category C — Host-marked integration & manual E2E (mostly DONE this session)

- [x] **`tests/integration/test_mc_autonomy_live.py`** (M12.3 T12.3.6) — ✅ **not actually host-marked.** Its header: *"runs in the normal pytest suite (no hardware mark needed — fully self-contained)"* (responder + fake camera + fake policy). Already part of the 833 passing tests.
- [x] **`tests/test_mc_packaging.py`** (M12.1 T12.1.7) — ✅ **verified this session.** `pytest -o addopts="" -m toolchain` built the PyInstaller sidecar via `app/scripts/build-sidecar.sh` and the binary served `/api/health` (1 passed, 14.9s). Needs PyInstaller (installed); no hardware.
- [⚠️] **`tests/integration/test_mc_live.py`** (M12.1) — **does NOT exist.** The M12.1 plan names this file but it was never created. The present live-agent test is `tests/integration/test_agent_live.py` (hardware-marked, needs `PIBOT_TEST_HOST`). Plan/reality mismatch.
- [ ] **macOS embedded-WebDriver E2E suite** (M12.5 T12.5.7) — STILL BLOCKED (the only genuinely-blocked part of C): `app/e2e/{connect,teleop,estop,autonomy,provisioning}.e2e.ts` need a built debug `.app` + WKWebView GUI session + a real `pibotd` stand — not runnable headless. (`pnpm e2e` is also not a defined script in `app/package.json`.) Run on the dev M4 Max before V1.

---

## 6. TODO — Category D: V1 release gate (M12.5 T12.5.9)

`docs/mission-control-v1-signoff.md` is **PENDING**. Automated suites are green; the performance targets are all ⬜ pending and must be measured on the M4 Max:

- [ ] Teleop round-trip latency — USB serial (< 50 ms P99) and Wi-Fi/TCP (< 200 ms P99).
- [ ] Sidecar startup time (< 2 s); connect → first telemetry tick (< 5 s).
- [ ] E-stop latch response (< 100 ms).
- [ ] Autonomy drop-to-stop on link loss (≤ `watchdog_ms`).
- [ ] Metrics write throughput (≥ 20 snapshots/s) and ≤ 1 % loss at 10 Hz.
- [ ] Policy inference latency, stock π₀.₅ (< 500 ms P99) — hardware-dependent.
- [ ] Then fill the sign-off table and ship V1. (The §3 frontend integration must land first for the GUI flows to be real.)

---

## 7. Repo-state issues (NOT missing features — fix to avoid confusion)

- [x] **`scripts/check.sh` gate — ✅ NOW GREEN (this session).** Resolved the pre-existing WIP failures that had never let the full gate pass: 39 `ruff check` errors fixed (auto-fix + manual), repo-wide `ruff format` + `cargo fmt`, and **10 mypy errors** fixed — including **2 real bugs**: `with`→`async with` on `asyncio.timeout_at` in `policy_server.py` (would have raised `AttributeError` at runtime if the kill-timeout path hit), and `_ExecFn` retyped to its keyword-only `dry_run` convention in `ops.py`; plus `Image.LANCZOS`→`Image.Resampling.LANCZOS`. `tmp/` + `app_patched.py` git-ignored. Full gate: ruff/format/mypy clean · pytest **841** (91% cov) · frontend **123** · cargo fmt/clippy/test (9) green. *(The pre-existing failures were not caused by this session's frontend/doc work; mypy/format/clippy had simply never run because `ruff check` failed first.)*
- [x] **SPEC-3 M12.2–M12.5 — ✅ NOW COMMITTED (this session).** Commit `7275e08` on `m12-2-teleop-estop-video` (130 files: sidecar routes, Rust e-stop, all frontend, tests, runbook, sign-offs, plus the GUI integration + gate fixes). Unrelated firmware WIP (`pibot_esp32.ino`, `firmware/README.md`, `esp32-pca9685-pinout.mmd`) was deliberately left **unstaged** for a separate commit, per your choice. Not yet pushed.
- [x] **Stale plan `Status` headers — ✅ DONE (this session).** Updated to match reality:
  m7/m8/m9 → "Software shipped + committed; HIL pending"; m12-1 → "Shipped + committed";
  m12-3/m12-4/m12-5 → "Software complete in working tree but UNCOMMITTED" (+ the screen now
  mounted); the control-suite roadmap → "M0–M6 shipped, T6.8 hardware sign-off pending"; the
  mission-control roadmap → "M12.1 committed, M12.2–M12.5 uncommitted, release gate open."
- [x] **Reconcile the V1 sign-off overclaim — ✅ DONE (this session).**
  `docs/mission-control-v1-signoff.md` milestone rows now read "software + GUI · release gate
  open" with a dated GUI-integration correction note; frontend count updated 118 → 123.

---

## 8. Minor deviations from the plans (functionally fine, noted for accuracy)

- **`app/src/stores/notifyStore.ts`** — ✅ created + wired this session (§3); real OS-notification delivery via the Tauri plugin is now fully installed/registered/permission-gated (no longer a mock).
- **M10 closed-loop landed as a `ClosedLoopEnvironment` subclass** in `pibot/ml/closed_loop.py` rather than mutating `pibot_environment.apply_action` (documented deviation in the M10 plan status; safety regressions still green).
- **Closed-loop autonomy moved in-process inside `pibotd`** (`agent/autonomy.py` `AutonomyController` + `POST/DELETE /autonomy`); `pibot autonomy --run` is now a thin client (documented in the M11 status).

---

## 9. Post-V1 / explicitly deferred (in the specs, intentionally NOT in V1)

Not bugs or gaps — design-allowed future scope. Listed because they are "outlined in the specs."

- **FR-23** — WebRTC low-latency video track (COULD; the `WS /video` abstraction is kept WebRTC-ready).
- **FR-24** — Simultaneous multi-robot dashboards (COULD; V1 operates one active robot).
- **OQ-3** — Per-session video clip persistence (deferred; frames are ephemeral).
- **OQ-6** — Code-signing / notarization (deferred; ad-hoc/unsigned for personal use).
- **OQ-9** — Remote policy host management over SSH/launchd (post-V1; V1 manages the local server).
- **FR-17 (SHOULD)** — GUI-launched fine-tune is implemented behind an injected `train_cmd` factory (fake in CI; real command host-marked) — present but exercised only with a fake trainer.

---

## Appendix — verification evidence

**Test suites (working tree, 2026-06-12):**
- Python: `.venv/bin/pytest` → **833 passed, 8 deselected, 0 failed** (exit 0). Deselected = `hardware`/`toolchain`/host-marked integration.
- Frontend: `cd app && pnpm test` → **123 passed, 20 files** (exit 0; +5 this session — 4 `notifyStore` + 1 nav smoke). Typecheck + lint also clean.
- Rust: `cd app/src-tauri && cargo test` → **9 passed, 0 failed** (exit 0).

**Release-blocking regressions — confirmed to assert real behavior (not vacuous):**
- `tests/test_mc_safety_bypass.py` — drives the real `/api/control` relay; asserts an over-limit drive is NAK'd by the gate **and forwarded unmodified** (sidecar doesn't silently clamp); grep-guards that no `pibot/mc` code sends motion outside `AgentClient`; asserts cadence stops on relay disconnect.
- `tests/test_mc_estop_failsafe.py` — relays `/api/estop`→pibotd; e-stop still works with the telemetry socket closed. **The sidecar-process-killed path is tested in Rust**, not here: `app/src-tauri/src/commands.rs` `estop_now_posts_to_robot_with_bearer` posts to a fake HTTP server **with no sidecar running**, using the cached endpoint.
- `tests/test_mc_destructive_guard.py` — parametrized over every destructive kind; asserts `PermissionError` unless `confirmed=True` AND `guard_passed=True`; fuzzes bypass payloads (`{force:True}`, `{confirmed:True}` planted in args, …) — none execute.
- `tests/test_security_invariants.py` — scan globs extended to `pibot/mc/**/*.py`, `app/src-tauri/**/*.{json,toml}`, `app/src/**/*.{ts,tsx}` (lines 163-167); `test_mc_surfaces_contain_no_hardcoded_secrets`.

**Integration wiring confirmed:** all sidecar route modules registered in `pibot/mc/app.py:21-36`; Tauri commands registered in `app/src-tauri/src/lib.rs:59-65`; global e-stop shortcut in `lib.rs:108-115`.

**Integration gap (now resolved):** the audit found `Drive`/`Autonomy`/`Provisioning`/`EstopButton`/`notifyAlerts` with **zero mount sites** — only `Dashboard` was imported by `App.tsx`. This session wired all of them into `App.tsx` (nav bar + the five screens + the functional `EstopButton` + the `notifyStore` effect); a nav smoke test in `App.test.tsx` now asserts each screen renders. Real OS-notification delivery was also completed (the Tauri notification plugin is installed/registered/permission-gated — §3).
