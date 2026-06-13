import { useEffect, useState } from "react";

import EpisodeList from "../components/EpisodeList";
import FineTunePanel from "../components/FineTunePanel";
import MetricsChart from "../components/MetricsChart";
import SessionReplay from "../components/SessionReplay";
import type { Episode, McEndpoint } from "../lib/api/types";
import { useDataStore } from "../stores/dataStore";
import { useMetricsStore } from "../stores/metricsStore";

interface Props {
  ep: McEndpoint | null;
}

type Tab = "episodes" | "finetune" | "metrics";

export default function Data({ ep }: Props) {
  const [tab, setTab] = useState<Tab>("episodes");
  const [selectedEp, setSelectedEp] = useState<Episode | null>(null);

  const { episodes, runs, loading, error, fetchEpisodes, fetchRuns } = useDataStore();
  const { rows, fetchHistory, exportData, clear } = useMetricsStore();

  useEffect(() => {
    if (!ep) return;
    if (tab === "episodes") fetchEpisodes(ep);
    else if (tab === "finetune") fetchRuns(ep);
    else if (tab === "metrics") {
      const to = Date.now() / 1000;
      const from = to - 3600; // last hour
      fetchHistory(ep, { from, to });
    }
  }, [tab, ep]);

  async function handleExport(fmt: "csv" | "json") {
    if (!ep) return;
    const to = Date.now() / 1000;
    const from = to - 3600;
    const data = await exportData(ep, { from, to }, fmt);
    const mime = fmt === "csv" ? "text/csv" : "application/json";
    const blob = new Blob([data], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `telemetry.${fmt}`;
    a.click();
    // Defer revocation: WebKit (this app's WKWebView, and Safari/Firefox) may not have started
    // reading the blob by the time a.click() returns, and a synchronous revoke can abort the
    // download. A short timeout lets the download bind to the URL first.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const TABS: Array<{ id: Tab; label: string }> = [
    { id: "episodes", label: "Episodes" },
    { id: "finetune", label: "Fine-Tune" },
    { id: "metrics", label: "Metrics" },
  ];

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="data-screen">
      {/* Tab bar */}
      <div className="flex gap-1 border-b border-zinc-700 pb-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => { setTab(t.id); setSelectedEp(null); clear(); }}
            className={`px-3 py-1.5 text-sm rounded-t ${
              tab === t.id
                ? "bg-zinc-700 text-white"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
            data-testid={`tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {!ep && (
        <p className="text-xs text-zinc-500">Connect to a robot to view data.</p>
      )}

      {loading && <p className="text-xs text-zinc-400">Loading…</p>}
      {error && <p className="text-xs text-red-400">{error}</p>}

      {tab === "episodes" && ep && (
        <div className="flex flex-col gap-3">
          <EpisodeList episodes={episodes} onSelect={setSelectedEp} />
          {selectedEp && (
            <div className="rounded border border-zinc-700 p-3 flex flex-col gap-2">
              <p className="text-xs font-medium text-zinc-300">
                {selectedEp.id} — {selectedEp.task}
              </p>
              <p className="text-xs text-zinc-500">
                {selectedEp.length} frames · {new Date(selectedEp.started * 1000).toLocaleString()}
              </p>
              <SessionReplay events={[]} />
            </div>
          )}
        </div>
      )}

      {tab === "finetune" && ep && (
        <FineTunePanel ep={ep} runs={runs} />
      )}

      {tab === "metrics" && ep && (
        <div className="flex flex-col gap-3">
          <div className="flex gap-2">
            <button
              onClick={() => handleExport("csv")}
              className="rounded bg-zinc-700 px-3 py-1.5 text-xs text-white hover:bg-zinc-600"
              data-testid="export-csv"
            >
              Export CSV
            </button>
            <button
              onClick={() => handleExport("json")}
              className="rounded bg-zinc-700 px-3 py-1.5 text-xs text-white hover:bg-zinc-600"
              data-testid="export-json"
            >
              Export JSON
            </button>
          </div>
          <MetricsChart rows={rows} field="temp_c" />
          <MetricsChart rows={rows} field="last_infer_ms" />
        </div>
      )}
    </div>
  );
}
