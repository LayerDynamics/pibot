import { create } from "zustand";

import type { McEndpoint, PolicyLink } from "../lib/api/types";

const STALE_THRESHOLD_MS = 1000;

interface AutonomyState {
  running: boolean;
  policy: PolicyLink | null;
  stale: boolean;
  error: string | null;
  start: (
    ep: McEndpoint,
    prompt: string,
    maxSpeed?: number,
    controlHz?: number,
  ) => Promise<void>;
  stop: (ep: McEndpoint) => Promise<void>;
  updateFromSnapshot: (policy: PolicyLink | null) => void;
  reset: () => void;
}

async function authed(ep: McEndpoint, path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${ep.url}${path}`, {
    ...init,
    headers: { ...(init.headers ?? {}), Authorization: `Bearer ${ep.token}` },
  });
}

export const useAutonomyStore = create<AutonomyState>((set) => ({
  running: false,
  policy: null,
  stale: false,
  error: null,

  start: async (ep, prompt, maxSpeed, controlHz) => {
    set({ error: null });
    const body: Record<string, unknown> = { prompt };
    if (maxSpeed !== undefined) body["max_speed"] = maxSpeed;
    if (controlHz !== undefined) body["control_hz"] = controlHz;
    try {
      const r = await authed(ep, "/api/autonomy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const text = await r.text();
        set({ error: `start failed (${r.status}): ${text}` });
        return;
      }
      set({ running: true, error: null });
    } catch (e) {
      set({ error: String(e) });
    }
  },

  stop: async (ep) => {
    set({ error: null });
    try {
      const r = await authed(ep, "/api/autonomy", { method: "DELETE" });
      if (!r.ok) {
        const text = await r.text();
        set({ error: `stop failed (${r.status}): ${text}` });
        return;
      }
      set({ running: false, error: null });
    } catch (e) {
      set({ error: String(e) });
    }
  },

  updateFromSnapshot: (policy) => {
    const stale =
      policy !== null &&
      typeof policy.chunk_age_ms === "number" &&
      policy.chunk_age_ms > STALE_THRESHOLD_MS;
    set({ policy, stale });
  },

  reset: () => set({ running: false, policy: null, stale: false, error: null }),
}));
