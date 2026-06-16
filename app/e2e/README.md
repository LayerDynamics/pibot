# PiBot Mission Control — E2E Suite (T12.5.7 / OQ-11)

## Status: **Manual / host-marked** — requires real hardware stand

This suite exercises the full stack: built debug `.app` + WKWebView + Rust core +
bundled sidecar against a real `pibotd` on the responder/Arduino-echo stand.

### Why not automated in CI

Per SPEC-3 §4.2 and CLAUDE.md E2E rules, an E2E test that exercises a "complete user-facing
workflow through the entire real system" cannot mock the hardware transport, the WebView
rendering, or the Rust e-stop failsafe. The Tauri embedded-WebDriver plugin
(`tauri-webdriver-automation`) requires a built `.app` bundle and a macOS GUI session —
neither is available in the CI container.

Relabeling a Chromium/integration test as E2E would violate the CLAUDE.md honesty
requirement. These tests are therefore documented as **manual, host-marked** and
must be run on a developer machine before each release.

### Flows

| File | Flow | Assertion |
|------|------|-----------|
| `connect.e2e.ts` | Connect → telemetry values render | DOM contains temp, battery, transport badge |
| `teleop.e2e.ts` | Drive → ACK in DOM | Teleop ACK/latency visible in the status bar |
| `estop.e2e.ts` | E-stop latch + sidecar-killed failsafe | Red banner, cannot drive, re-connect required |
| `autonomy.e2e.ts` | Autonomy start→stop with fake policy | Policy-link chart renders, stop returns to idle |
| `provisioning.e2e.ts` | Flash dry-run → modal → guard checkbox required | Confirm button disabled without guard check |
| `arm.e2e.ts` | Arm tab home → jog → program → twin → e-stop/clear | Arm telemetry, program state, and the twin stay coherent on a real arm stand |

### How to run (macOS, developer machine)

```bash
# 1. Build the debug app (includes embedded-WebDriver plugin)
cd app && pnpm tauri build --debug

# 2. Start a pibotd stand (responder or Arduino-echo)
pibot agent --transport responder

# 3. Run the E2E harness
pnpm e2e
```

### Hardware stand requirements

- macOS 14+ (Sonoma or Sequoia)
- Tauri debug build with `tauri-plugin-webdriver` enabled
- `pibotd` reachable at `http://127.0.0.1:<agent_port>`
- Robot inventory entry for `testbot`
- For `arm.e2e.ts`: an arm-enabled robot/stand with the Arm screen surfaces configured

### Release gate

The five core Mission Control flows must pass on the developer's M4 Max before V1 ships.
For an arm release, `arm.e2e.ts` is additionally required on an arm-enabled stand.
Results are recorded in `docs/mission-control-v1-signoff.md` and `docs/hardware-arm-signoff.md`.
