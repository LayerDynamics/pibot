import type { FineTuneRun, McEndpoint } from "../lib/api/types";
import { useDataStore } from "../stores/dataStore";

interface Props {
  ep: McEndpoint | null;
  runs: FineTuneRun[];
}

const STATUS_COLOR: Record<string, string> = {
  queued: "text-zinc-400",
  running: "text-yellow-400",
  done: "text-green-400",
  error: "text-red-400",
};

export default function FineTunePanel({ ep, runs }: Props) {
  const { serveCheckpoint } = useDataStore();

  async function handleServe(runId: string) {
    if (!ep) return;
    try {
      await serveCheckpoint(ep, runId);
    } catch {
      /* error surfaced by store */
    }
  }

  if (runs.length === 0) {
    return (
      <p className="text-xs text-zinc-500" data-testid="finetune-panel-empty">
        No fine-tune runs yet.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-2" data-testid="finetune-panel">
      {runs.map((run) => (
        <li
          key={run.id}
          className="rounded bg-zinc-800 px-3 py-2 text-sm flex flex-col gap-1"
        >
          <div className="flex items-center gap-3">
            <span className={`text-xs font-medium ${STATUS_COLOR[run.status] ?? "text-zinc-400"}`}>
              {run.status}
            </span>
            <span className="flex-1 truncate text-xs text-zinc-400">{run.dataset}</span>
            {run.status === "done" && !run.served && ep && (
              <button
                onClick={() => handleServe(run.id)}
                className="text-xs rounded bg-zinc-700 px-2 py-1 text-white hover:bg-zinc-600"
              >
                Serve
              </button>
            )}
            {run.served && (
              <span className="text-xs text-green-400">Serving</span>
            )}
          </div>
          {run.checkpoint_out && (
            <span className="truncate text-xs text-zinc-500" title={run.checkpoint_out}>
              {run.checkpoint_out}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
