import { create } from "zustand";

import { gamepadMap } from "../lib/gamepadMap";
import { useTeleopStore } from "./teleopStore";

interface GamepadState {
  active: boolean;
  _rafId: number | null;
  start: () => void;
  stop: () => void;
}

// Last (v, w) emitted from the gamepad. pollLoop runs at rAF (60-120 Hz); without this an
// unchanged stick would flood the socket every frame. Reset to null whenever the gamepad is not
// the active controller (no pad, no open socket, or the keyboard has priority) so control always
// resumes with a fresh frame rather than being wrongly suppressed as "unchanged".
let lastV: number | null = null;
let lastW: number | null = null;

function pollLoop(rafId: { current: number | null }): void {
  const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
  let emitted = false;
  for (const gp of gamepads) {
    if (!gp || !gp.connected) continue;
    const { v, w } = gamepadMap(gp.axes, gp.buttons);
    const { ws, pressedKeys } = useTeleopStore.getState();
    // Keyboard takes priority — yield the gamepad entirely while keys are held.
    if (pressedKeys.size > 0) break;
    if (ws && ws.readyState === WebSocket.OPEN) {
      // Only emit when the stick actually moved: the sidecar's CadenceKeeper already re-sends
      // the last drive to feed pibotd's watchdog, so an identical frame every tick is redundant.
      if (v !== lastV || w !== lastW) {
        ws.send(
          JSON.stringify(
            v === 0 && w === 0 ? { cmd: "stop", args: {} } : { cmd: "drive", args: { v, w } },
          ),
        );
        lastV = v;
        lastW = w;
      }
      emitted = true;
    }
    break; // use the first connected gamepad only
  }
  if (!emitted) {
    lastV = null;
    lastW = null;
  }
  rafId.current = requestAnimationFrame(() => pollLoop(rafId));
}

export const useGamepadStore = create<GamepadState>((set, get) => {
  const rafId = { current: null as number | null };
  return {
    active: false,
    _rafId: null,

    start: () => {
      if (get().active) return;
      lastV = null; // fresh session: don't suppress the first frame against a stale value
      lastW = null;
      pollLoop(rafId);
      set({ active: true });
    },

    stop: () => {
      if (rafId.current !== null) {
        cancelAnimationFrame(rafId.current);
        rafId.current = null;
      }
      set({ active: false });
    },
  };
});
