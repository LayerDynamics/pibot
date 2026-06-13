import { create } from "zustand";

import { teleopMap } from "../lib/teleopMap";

interface TeleopState {
  pressedKeys: Set<string>;
  ws: WebSocket | null;
  setWs: (ws: WebSocket | null) => void;
  keyDown: (code: string) => void;
  keyUp: (code: string) => void;
  stop: () => void;
  reset: () => void;
}

function sendFrame(ws: WebSocket | null, cmd: string, args?: Record<string, unknown>): void {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ cmd, args: args ?? {} }));
  }
}

export const useTeleopStore = create<TeleopState>((set, get) => ({
  pressedKeys: new Set<string>(),
  ws: null,

  setWs: (ws) => set({ ws }),

  keyDown: (code) => {
    const { pressedKeys, ws } = get();
    if (code === "Escape") {
      sendFrame(ws, "stop");
      set({ pressedKeys: new Set<string>() });
      return;
    }
    // Browsers fire keydown repeatedly while a key is held. The held set is unchanged, so the
    // frame would be identical — skip it. The sidecar's CadenceKeeper keeps re-sending the last
    // drive to feed pibotd's watchdog, so suppressing the repeat does not stall the robot.
    if (pressedKeys.has(code)) return;
    const next = new Set(pressedKeys);
    next.add(code);
    const { v, w } = teleopMap(next);
    if (v === 0 && w === 0) {
      sendFrame(ws, "stop");
    } else {
      sendFrame(ws, "drive", { v, w });
    }
    set({ pressedKeys: next });
  },

  keyUp: (code) => {
    const { pressedKeys, ws } = get();
    const next = new Set(pressedKeys);
    next.delete(code);
    const { v, w } = teleopMap(next);
    if (v === 0 && w === 0) {
      sendFrame(ws, "stop");
    } else {
      sendFrame(ws, "drive", { v, w });
    }
    set({ pressedKeys: next });
  },

  stop: () => {
    const { ws } = get();
    sendFrame(ws, "stop");
    set({ pressedKeys: new Set<string>() });
  },

  reset: () => {
    set({ pressedKeys: new Set<string>(), ws: null });
  },
}));
