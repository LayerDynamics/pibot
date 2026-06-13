import { create } from "zustand";

import { gamepadMap } from "../lib/gamepadMap";
import { useTeleopStore } from "./teleopStore";

interface GamepadState {
  active: boolean;
  _rafId: number | null;
  start: () => void;
  stop: () => void;
}

function pollLoop(rafId: { current: number | null }): void {
  const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
  for (const gp of gamepads) {
    if (!gp || !gp.connected) continue;
    const { v, w } = gamepadMap(gp.axes, gp.buttons);
    const { ws, pressedKeys } = useTeleopStore.getState();
    // Only emit gamepad frames if no keyboard keys are held (keyboard takes priority).
    if (pressedKeys.size > 0) continue;
    if (ws && ws.readyState === WebSocket.OPEN) {
      if (v === 0 && w === 0) {
        ws.send(JSON.stringify({ cmd: "stop", args: {} }));
      } else {
        ws.send(JSON.stringify({ cmd: "drive", args: { v, w } }));
      }
    }
    break; // use the first connected gamepad only
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
