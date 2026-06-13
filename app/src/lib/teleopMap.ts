/** Maximum linear velocity (m/s) sent to the robot. */
export const MAX_V = 0.5;
/** Maximum angular velocity (rad/s) sent to the robot. */
export const MAX_W = 1.0;

export interface DriveCmd {
  v: number;
  w: number;
}

const clamp = (val: number, limit: number) => Math.max(-limit, Math.min(limit, val));

/**
 * Map a set of currently-pressed key codes to a (v, w) drive command.
 * Returns {v:0, w:0} when Escape is held or no drive keys are active.
 */
export function teleopMap(keys: ReadonlySet<string>): DriveCmd {
  if (keys.has("Escape")) {
    return { v: 0, w: 0 };
  }

  let v = 0;
  let w = 0;

  if (keys.has("KeyW") || keys.has("ArrowUp")) v += MAX_V;
  if (keys.has("KeyS") || keys.has("ArrowDown")) v -= MAX_V;
  if (keys.has("KeyA") || keys.has("ArrowLeft")) w += MAX_W;
  if (keys.has("KeyD") || keys.has("ArrowRight")) w -= MAX_W;

  return { v: clamp(v, MAX_V), w: clamp(w, MAX_W) };
}
