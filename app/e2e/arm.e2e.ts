/**
 * @host-marked — requires built .app + arm-enabled hardware stand (see README.md)
 *
 * Flow: Arm screen home → jog → program run/stop → twin tracks telemetry → e-stop/clear
 * Assertions: Joint state updates render; twin stays live; program status surfaces; e-stop latches
 */
export const meta = {
  flow: "arm",
  status: "host-marked",
  reason: "Requires macOS GUI session + built Tauri .app + arm-enabled pibotd stand",
};

/*
Manual steps:
  1. Connect to an arm-enabled robot entry (for example "testbot") and open the Arm tab.
  2. Click Home on one conservative bench-safe joint.
  Expected:
    a. The joint row flips from "not homed" to "homed"
    b. The twin stays live; no error banner appears
  3. Hold one jog button for ~0.5 s, then release.
  Expected:
    a. The joint angle readout changes
    b. The 3-D twin follows the same motion
  4. Record a pose, add a simple wait or moveJ step, save the program, and click "Run".
  Expected:
    a. Program status appears with the current step/kind
    b. "Stop program" halts it and the stopped status surfaces
  5. Click the Arm E-Stop button, then Clear.
  Expected:
    a. The latched badge appears immediately and motion controls lock out
    b. Clear releases the latch and controls become usable again
*/
