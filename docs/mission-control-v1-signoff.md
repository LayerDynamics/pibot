# Mission Control V1 Sign-off (SPEC-3 M12)

The acceptance bar for the PiBot Mission Control V1 release: every milestone green, all
automated suites passing, and the host-marked E2E flows manually verified on a real
hardware stand.

> **Status: PENDING — automated suites green; host-marked E2E and hardware-dependent
> performance targets require the M4 Max + Pi stand.**

## Automated suite results (recorded 2026-06-12)

| Suite | Count | Result |
|-------|-------|--------|
| Python (pytest) | 833 passed, 8 deselected | ✅ green |
| Frontend (vitest) | 123 passed, 20 files | ✅ green |
| Rust (cargo test) | 9 passed | ✅ green |
| Total regressions | 0 | ✅ |

Run to reproduce:

```bash
# Python
python -m pytest --tb=short -q

# Frontend
cd app && pnpm test --run

# Rust
cd app && cargo test --manifest-path src-tauri/Cargo.toml
```

## Milestone completion checklist

"Complete" here means **software + frontend integration** is done and all automated suites
are green. It does **not** include the release gate (hardware performance measurement +
manual E2E), which is still open — see the Performance and E2E sections below.

| Milestone | Description | Status |
|-----------|-------------|--------|
| M12.1 | Shell + sidecar + connect + dashboard | ✅ complete (committed) |
| M12.2 | Teleop, E-stop, video feed | ✅ software + GUI · release gate open |
| M12.3 | Autonomy + policy server | ✅ software + GUI · release gate open |
| M12.4 | Data / metrics / sessions | ✅ software + GUI · release gate open |
| M12.5 | Provisioning / hardening / release | ✅ software + GUI · release gate + E2E open |

> **GUI-integration correction (2026-06-12).** Through M12.1 the App shell mounted only the
> Dashboard; the M12.2–M12.5 screens (Drive/Autonomy/Data/Provisioning), the functional
> `EstopButton`, and the native-notification helper were implemented and unit-tested but
> **not wired into `App.tsx`** — the on-screen e-stop was a no-op placeholder and OS
> notifications never fired (only the Rust `Ctrl+Shift+E` global hotkey worked). These were
> integrated on 2026-06-12: a screen-navigation bar mounts all five screens, the functional
> `EstopButton` sits in the top bar, and `notifyStore` wires the telemetry alert stream into
> `notifyAlerts`. A navigation smoke test (`App.test.tsx`) guards this.
>
> **Real OS-notification delivery is now wired** (FR-22): the `@tauri-apps/plugin-notification`
> package + the Rust `tauri-plugin-notification` are installed, registered
> (`.plugin(tauri_plugin_notification::init())`), and capability-granted (`notification:default`);
> `notify.ts` requests permission then delivers, and the vite mock is scoped to tests only.
> **Still open:** the release-gate performance measurements and the manual E2E flows below.

## Performance targets

Hardware-dependent targets require a real Pi + M4 Max stand. Mark each when verified.

| Target | Threshold | Result | Date | Notes |
|--------|-----------|--------|------|-------|
| Teleop round-trip latency (USB serial) | < 50 ms P99 | ⬜ pending | | |
| Teleop round-trip latency (Wi-Fi/TCP) | < 200 ms P99 | ⬜ pending | | |
| Sidecar startup time | < 2 s | ⬜ pending | | |
| Connect → first telemetry tick | < 5 s | ⬜ pending | | |
| E-stop latch response | < 100 ms | ⬜ pending | | |
| Autonomy drop-to-stop on link loss | ≤ watchdog_ms | ⬜ pending | | validated in-process by test suite |
| Metrics write throughput | ≥ 20 snapshots/s | ⬜ pending | | flush_size=50 batch |
| Policy infer latency (stock π₀.₅) | < 500 ms P99 | ⬜ pending | | hardware-dependent |

## Host-marked E2E flows (macOS, hardware stand required)

See [app/e2e/README.md](../app/e2e/README.md) for the full procedure.

| Flow | File | Result | Date | Operator |
|------|------|--------|------|----------|
| Connect → telemetry render | connect.e2e.ts | ⬜ pending | | |
| Teleop drive → ACK in DOM | teleop.e2e.ts | ⬜ pending | | |
| E-stop latch + sidecar-killed failsafe | estop.e2e.ts | ⬜ pending | | |
| Autonomy start→stop with fake policy | autonomy.e2e.ts | ⬜ pending | | |
| Flash dry-run → guard checkbox required | provisioning.e2e.ts | ⬜ pending | | |

## Security invariants

All security regression tests pass as part of the automated suite above.

| Check | Test | Status |
|-------|------|--------|
| No hardcoded secrets in mc/ or app/ | `test_mc_surfaces_contain_no_hardcoded_secrets` | ✅ |
| Per-launch token not tracked by git | `test_per_launch_token_not_tracked_by_git` | ✅ |
| Tauri CSP non-wildcard | `test_tauri_conf_has_non_wildcard_csp` | ✅ |
| No blanket shell/fs capabilities | `test_tauri_capabilities_no_blanket_shell_or_fs` | ✅ |
| Destructive ops require both gates | `test_mc_destructive_guard.py` (42 cases) | ✅ |

## Version

- Python package (`pibot`): `0.0.0` → bump to `0.1.0` before tagging
- Desktop app: `0.1.0` (app/package.json, app/src-tauri/tauri.conf.json, app/src-tauri/Cargo.toml)

Version bump procedure:

```bash
# Python package
sed -i '' 's/^version = "0.0.0"/version = "0.1.0"/' pyproject.toml

# Confirm
python -m pytest --tb=short -q  # must still pass
git tag -a v0.1.0 -m "Mission Control V1"
```

## Sign-off procedure

1. Run all three automated suites — zero failures, zero regressions.
2. Manually execute all five host-marked E2E flows (see table above).
3. Record performance target measurements on the hardware stand.
4. Fill the results tables above.
5. Bump `pyproject.toml` version to `0.1.0`.
6. Commit, tag `v0.1.0`, push.

**Release is blocked until all three suite rows show ✅ and all five E2E rows are filled.**
