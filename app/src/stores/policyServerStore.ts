import { create } from "zustand";

import type { McEndpoint } from "../lib/api/types";

export type PolicyServerStatus = "stopped" | "starting" | "running" | "error";

export interface PolicyServerInfo {
  host: string;
  port: number;
  pid: number | null;
  checkpoint: string | null;
  state: PolicyServerStatus;
  last_infer_ms: number | null;
}

interface PolicyServerState extends PolicyServerInfo {
  error: string | null;
  start: (ep: McEndpoint, checkpoint: string) => Promise<void>;
  stop: (ep: McEndpoint) => Promise<void>;
  refresh: (ep: McEndpoint) => Promise<void>;
  reset: () => void;
}

const DEFAULTS: PolicyServerInfo = {
  host: "127.0.0.1",
  port: 8000,
  pid: null,
  checkpoint: null,
  state: "stopped",
  last_infer_ms: null,
};

async function authed(ep: McEndpoint, path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${ep.url}${path}`, {
    ...init,
    headers: { ...(init.headers ?? {}), Authorization: `Bearer ${ep.token}` },
  });
}

function applyInfo(set: (partial: Partial<PolicyServerState>) => void, info: PolicyServerInfo) {
  set(info);
}

export const usePolicyServerStore = create<PolicyServerState>((set) => ({
  ...DEFAULTS,
  error: null,

  start: async (ep, checkpoint) => {
    set({ error: null });
    try {
      const r = await authed(ep, "/api/policy-server", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ checkpoint }),
      });
      const data = (await r.json()) as PolicyServerInfo;
      applyInfo(set, data);
      if (!r.ok) {
        set({ error: `start failed (${r.status})` });
      }
    } catch (e) {
      set({ error: String(e) });
    }
  },

  stop: async (ep) => {
    set({ error: null });
    try {
      const r = await authed(ep, "/api/policy-server", { method: "DELETE" });
      const data = (await r.json()) as PolicyServerInfo;
      applyInfo(set, data);
      if (!r.ok) {
        set({ error: `stop failed (${r.status})` });
      }
    } catch (e) {
      set({ error: String(e) });
    }
  },

  refresh: async (ep) => {
    try {
      const r = await authed(ep, "/api/policy-server");
      if (r.ok) {
        const data = (await r.json()) as PolicyServerInfo;
        applyInfo(set, data);
      }
    } catch {
      // refresh is best-effort; don't overwrite existing error
    }
  },

  reset: () => set({ ...DEFAULTS, error: null }),
}));
