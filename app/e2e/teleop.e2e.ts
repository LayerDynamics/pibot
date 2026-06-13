/**
 * @host-marked — requires built .app + hardware stand (see README.md)
 *
 * Flow: Drive → ACK in DOM
 * Assertions: Teleop ACK/latency visible in the status bar
 */
export const meta = {
  flow: "teleop",
  status: "host-marked",
  reason: "Requires macOS GUI session + built Tauri .app + pibotd stand",
};

/*
Manual steps:
  1. Connect to "testbot" (see connect flow)
  2. Navigate to Teleop tab
  3. Use WASD / gamepad to drive for 2 s
  Expected: Status bar shows ACK latency < 200 ms; no "disconnected" banner
*/
