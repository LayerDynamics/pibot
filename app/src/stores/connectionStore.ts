import { create } from "zustand";

export type ConnState = "disconnected" | "connecting" | "connected";

interface ConnectionState {
  state: ConnState;
  robot: string | null;
  error: string | null;
  estopLatched: boolean;
  setState: (s: ConnState, robot?: string | null) => void;
  setError: (e: string | null) => void;
  setEstopLatched: (latched: boolean) => void;
}

export const useConnectionStore = create<ConnectionState>((set) => ({
  state: "disconnected",
  robot: null,
  error: null,
  estopLatched: false,
  setState: (s, robot = null) => set({ state: s, robot, error: null }),
  setError: (e) => set({ error: e, state: "disconnected" }),
  setEstopLatched: (latched) => set({ estopLatched: latched }),
}));
