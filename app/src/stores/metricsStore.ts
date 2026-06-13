import { create } from "zustand";

import type { HistoryQuery, McEndpoint, TelemetryRow } from "../lib/api/types";

interface MetricsState {
  rows: TelemetryRow[];
  loading: boolean;
  error: string | null;

  fetchHistory: (ep: McEndpoint, query: HistoryQuery) => Promise<void>;
  exportData: (ep: McEndpoint, query: HistoryQuery, fmt: "csv" | "json") => Promise<string>;
  clear: () => void;
}

function headers(ep: McEndpoint) {
  return { Authorization: `Bearer ${ep.token}` };
}

export const useMetricsStore = create<MetricsState>((set) => ({
  rows: [],
  loading: false,
  error: null,

  async fetchHistory(ep, query) {
    set({ loading: true, error: null });
    try {
      const params = new URLSearchParams({
        from: String(query.from),
        to: String(query.to),
        ...(query.fields ? { fields: query.fields.join(",") } : {}),
      });
      const r = await fetch(`${ep.url}/api/telemetry/history?${params}`, {
        headers: headers(ep),
      });
      if (!r.ok) throw new Error(`history fetch failed: ${r.status}`);
      const data = await r.json();
      set({ rows: data.rows ?? [] });
    } catch (e) {
      set({ error: String(e) });
    } finally {
      set({ loading: false });
    }
  },

  async exportData(ep, query, fmt) {
    const params = new URLSearchParams({
      from: String(query.from),
      to: String(query.to),
      fmt,
    });
    const r = await fetch(`${ep.url}/api/telemetry/export?${params}`, {
      headers: headers(ep),
    });
    if (!r.ok) throw new Error(`export failed: ${r.status}`);
    return r.text();
  },

  clear: () => set({ rows: [], error: null }),
}));
