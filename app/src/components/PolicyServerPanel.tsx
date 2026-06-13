import { invoke } from "@tauri-apps/api/core";

import type { McEndpoint } from "../lib/api/types";
import type { PolicyServerStatus } from "../stores/policyServerStore";
import { usePolicyServerStore } from "../stores/policyServerStore";

const STATUS_COLORS: Record<PolicyServerStatus, string> = {
  stopped: "bg-zinc-600",
  starting: "bg-yellow-500",
  running: "bg-green-400",
  error: "bg-red-500",
};

interface Props {
  ep: McEndpoint | null;
}

export default function PolicyServerPanel({ ep }: Props) {
  const { state, pid, checkpoint, last_infer_ms, error, start, stop } = usePolicyServerStore();

  async function handlePickAndStart() {
    if (!ep) return;
    const path = await invoke<string | null>("pick_path");
    if (path) {
      await start(ep, path);
    }
  }

  async function handleStop() {
    if (!ep) return;
    await stop(ep);
  }

  return (
    <div
      data-testid="policy-server-panel"
      className="flex flex-col gap-3 rounded-md border border-zinc-700 bg-zinc-900 p-4"
    >
      <div className="flex items-center gap-2">
        <div className={`h-2 w-2 rounded-full ${STATUS_COLORS[state]}`} />
        <span className="text-sm font-medium text-zinc-300 capitalize">{state}</span>
        {pid != null && (
          <span className="ml-auto text-xs text-zinc-500">pid {pid}</span>
        )}
      </div>

      {checkpoint && (
        <p className="truncate text-xs text-zinc-500" title={checkpoint}>
          {checkpoint}
        </p>
      )}

      {last_infer_ms != null && (
        <p className="text-xs text-zinc-400">
          Last infer: <span className="text-zinc-200">{last_infer_ms.toFixed(1)} ms</span>
        </p>
      )}

      <div className="flex gap-2">
        <button
          onClick={handlePickAndStart}
          disabled={state === "running" || state === "starting" || !ep}
          className="rounded bg-zinc-700 px-3 py-1.5 text-xs text-white hover:bg-zinc-600 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Pick checkpoint & start
        </button>
        <button
          onClick={handleStop}
          disabled={state === "stopped" || !ep}
          className="rounded bg-zinc-700 px-3 py-1.5 text-xs text-white hover:bg-zinc-600 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Stop
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-400">{error}</p>
      )}
    </div>
  );
}
