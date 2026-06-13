/**
 * @host-marked — requires built .app + hardware stand (see README.md)
 *
 * Flow: Connect → telemetry values render
 * Assertions: DOM contains temp, battery, and transport badge
 */
export const meta = {
  flow: "connect",
  status: "host-marked",
  reason: "Requires macOS GUI session + built Tauri .app + pibotd stand",
};

/*
Manual steps:
  1. Launch Mission Control debug build
  2. Enter robot ID "testbot" and token in Connect screen
  3. Click "Connect"
  Expected: Dashboard shows temp_c, battery_v values and green transport badge within 5 s
*/
