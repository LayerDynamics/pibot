import { create } from "zustand";

import { alerts as computeAlerts } from "../lib/alerts";
import type { Snapshot } from "../lib/api/types";

interface TelemetryState {
  snapshot: Snapshot | null;
  alerts: string[];
  setSnapshot: (s: Snapshot) => void;
  clear: () => void;
}

export const useTelemetryStore = create<TelemetryState>((set) => ({
  snapshot: null,
  alerts: [],
  setSnapshot: (s) => set({ snapshot: s, alerts: computeAlerts(s) }),
  clear: () => set({ snapshot: null, alerts: [] }),
}));
