import { MAX_V, MAX_W } from "./teleopMap";
import type { DriveCmd } from "./teleopMap";

/** Axis values within this range are treated as zero (stick resting position noise). */
export const DEADZONE = 0.12;

/** Face button index that maps to "stop" (A on Xbox, Cross on PlayStation). */
const STOP_BUTTON = 0;

const clamp = (val: number, limit: number) => Math.max(-limit, Math.min(limit, val));

/**
 * Scale an axis value through the deadzone so the usable range starts at 0.
 * Returns 0 within the deadzone; scales linearly to ±1 at ±1.
 */
function applyDeadzone(v: number): number {
  if (Math.abs(v) < DEADZONE) return 0;
  const sign = v > 0 ? 1 : -1;
  return sign * ((Math.abs(v) - DEADZONE) / (1 - DEADZONE));
}

/**
 * Map gamepad axes + buttons to a (v, w) drive command.
 *
 * Standard gamepad layout:
 *   axes[1] = left-stick Y  (-1 = forward, +1 = backward — gamepad convention)
 *   axes[2] = right-stick X (-1 = left, +1 = right)
 */
export function gamepadMap(axes: readonly number[], buttons: readonly GamepadButton[]): DriveCmd {
  if (buttons[STOP_BUTTON]?.pressed) {
    return { v: 0, w: 0 };
  }

  const rawV = -(axes[1] ?? 0);  // invert: gamepad -1 = forward → positive v
  const rawW = -(axes[2] ?? 0);  // invert: gamepad +1 = right → negative w

  const v = clamp(applyDeadzone(rawV) * MAX_V, MAX_V);
  const w = clamp(applyDeadzone(rawW) * MAX_W, MAX_W);

  return { v, w };
}
