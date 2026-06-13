import { create } from "zustand";

import type { Episode, FineTuneRun, McEndpoint } from "../lib/api/types";

interface DataState {
  episodes: Episode[];
  runs: FineTuneRun[];
  loading: boolean;
  error: string | null;

  fetchEpisodes: (ep: McEndpoint) => Promise<void>;
  fetchRuns: (ep: McEndpoint) => Promise<void>;
  serveCheckpoint: (ep: McEndpoint, runId: string) => Promise<void>;
}

function headers(ep: McEndpoint) {
  return { Authorization: `Bearer ${ep.token}` };
}

export const useDataStore = create<DataState>((set) => ({
  episodes: [],
  runs: [],
  loading: false,
  error: null,

  async fetchEpisodes(ep) {
    set({ loading: true, error: null });
    try {
      const r = await fetch(`${ep.url}/api/episodes`, { headers: headers(ep) });
      if (!r.ok) throw new Error(`episodes fetch failed: ${r.status}`);
      const data = await r.json();
      set({ episodes: data.episodes ?? [] });
    } catch (e) {
      set({ error: String(e) });
    } finally {
      set({ loading: false });
    }
  },

  async fetchRuns(ep) {
    set({ loading: true, error: null });
    try {
      const r = await fetch(`${ep.url}/api/finetune`, { headers: headers(ep) });
      if (!r.ok) throw new Error(`finetune fetch failed: ${r.status}`);
      const data = await r.json();
      set({ runs: data.runs ?? [] });
    } catch (e) {
      set({ error: String(e) });
    } finally {
      set({ loading: false });
    }
  },

  async serveCheckpoint(ep, runId) {
    const r = await fetch(`${ep.url}/api/finetune/${runId}/serve`, {
      method: "POST",
      headers: headers(ep),
    });
    if (!r.ok) throw new Error(`serve failed: ${r.status}`);
    // refresh runs after serving
    const data = await (
      await fetch(`${ep.url}/api/finetune`, { headers: headers(ep) })
    ).json();
    set({ runs: data.runs ?? [] });
  },
}));
