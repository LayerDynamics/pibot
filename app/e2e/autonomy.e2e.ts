/**
 * @host-marked — requires built .app + hardware stand (see README.md)
 *
 * Flow: Autonomy start → stop with fake policy
 * Assertions: Policy-link chart renders; stop returns to idle
 */
export const meta = {
  flow: "autonomy",
  status: "host-marked",
  reason: "Requires macOS GUI session + built Tauri .app + pibotd stand",
};

/*
Manual steps:
  1. Connect to "testbot"
  2. Launch a fake policy server: python -m pibot.control.policy_server --mock
  3. Navigate to Autonomy tab, enter policy server URL, click "Start"
  Expected:
    a. Policy-link chart shows infer_ms values updating each cycle
    b. "Running" badge appears in the autonomy panel header
  4. Click "Stop"
  Expected:
    a. "Running" badge disappears; status returns to "Idle"
    b. No error banner
*/
