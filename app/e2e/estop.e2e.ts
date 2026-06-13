/**
 * @host-marked — requires built .app + hardware stand (see README.md)
 *
 * Flow: E-stop latch + sidecar-killed failsafe
 * Assertions: Red banner visible; drive inputs disabled; re-connect required
 */
export const meta = {
  flow: "estop",
  status: "host-marked",
  reason: "Requires macOS GUI session + built Tauri .app + pibotd stand",
};

/*
Manual steps:
  1. Connect to "testbot" and start driving
  2. Press the E-STOP button in the UI (or Escape key)
  Expected:
    a. Red "E-STOP LATCHED" banner appears immediately
    b. Teleop inputs are disabled (all commands return 403)
    c. Re-connect clears the latch (new session required)
  3. Kill the sidecar process externally
  Expected:
    a. App detects sidecar exit within 2 s
    b. UI shows "Sidecar offline" error state — cannot drive
*/
