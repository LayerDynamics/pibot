import { useState } from "react";

interface SessionEvent {
  ts: number;
  kind: string;
  data: unknown;
}

interface Props {
  events: SessionEvent[];
}

export default function SessionReplay({ events }: Props) {
  const [cursor, setCursor] = useState(0);

  if (events.length === 0) {
    return (
      <p className="text-xs text-zinc-500" data-testid="session-replay-empty">
        No events in this session.
      </p>
    );
  }

  const current = events[cursor];

  return (
    <div className="flex flex-col gap-3" data-testid="session-replay">
      <div className="rounded bg-zinc-800 p-3 text-sm">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-zinc-400 text-xs font-mono">
            {cursor + 1} / {events.length}
          </span>
          <span className="text-xs font-medium text-zinc-200">{current.kind}</span>
          <span className="ml-auto text-xs text-zinc-500">
            {current.ts.toFixed(3)}
          </span>
        </div>
        <pre className="text-xs text-zinc-400 overflow-auto max-h-32 whitespace-pre-wrap">
          {JSON.stringify(current.data, null, 2)}
        </pre>
      </div>

      <div className="flex items-center gap-2">
        <button
          data-testid="replay-prev"
          onClick={() => setCursor((c) => Math.max(0, c - 1))}
          disabled={cursor === 0}
          className="rounded bg-zinc-700 px-3 py-1 text-xs text-white hover:bg-zinc-600 disabled:opacity-40"
        >
          ‹ Prev
        </button>
        <input
          type="range"
          min={0}
          max={events.length - 1}
          value={cursor}
          onChange={(e) => setCursor(Number(e.target.value))}
          className="flex-1"
          data-testid="replay-scrubber"
        />
        <button
          data-testid="replay-next"
          onClick={() => setCursor((c) => Math.min(events.length - 1, c + 1))}
          disabled={cursor === events.length - 1}
          className="rounded bg-zinc-700 px-3 py-1 text-xs text-white hover:bg-zinc-600 disabled:opacity-40"
        >
          Next ›
        </button>
      </div>
    </div>
  );
}
