import * as Slider from "@radix-ui/react-slider";
import { useEffect, useRef, useState } from "react";

import PolicyLinkChart from "../components/PolicyLinkChart";
import { mcEndpoint } from "../lib/api/client";
import type { LatencySample } from "../lib/series";
import { LatencySeries, STALE_THRESHOLD_MS } from "../lib/series";
import { TASK_KEYS, TASK_PROMPTS } from "../lib/tasks";
import { useAutonomyStore } from "../stores/autonomyStore";
import { useTelemetryStore } from "../stores/telemetryStore";

export default function Autonomy() {
  const { running, policy, stale, error, start, stop, updateFromSnapshot } = useAutonomyStore();
  const snapshot = useTelemetryStore((s) => s.snapshot);

  const [selectedTask, setSelectedTask] = useState<string>("goal");
  const [customPrompt, setCustomPrompt] = useState<string>("");
  const [maxSpeed, setMaxSpeed] = useState<number>(0.3);
  const [controlHz, setControlHz] = useState<number>(20);

  const seriesRef = useRef(new LatencySeries());
  const [seriesSnap, setSeriesSnap] = useState<LatencySample[]>([]);

  // Keep autonomy store and latency series in sync with telemetry snapshot.
  useEffect(() => {
    const p = snapshot?.policy ?? null;
    updateFromSnapshot(p);
    if (p?.last_inference_ms != null) {
      const chunkAge = p.chunk_age_ms ?? 0;
      seriesRef.current.push({
        ts: snapshot?.ts ?? Date.now() / 1000,
        inferMs: p.last_inference_ms,
        stale: chunkAge > STALE_THRESHOLD_MS,
      });
      setSeriesSnap([...seriesRef.current.samples]);
    }
  }, [snapshot, updateFromSnapshot]);

  const prompt = customPrompt.trim() || TASK_PROMPTS[selectedTask] || "";

  async function handleStart() {
    const ep = await mcEndpoint();
    await start(ep, prompt, maxSpeed, controlHz);
  }

  async function handleStop() {
    const ep = await mcEndpoint();
    await stop(ep);
  }

  const policyConnected = policy?.connected;
  const inferMs = policy?.last_inference_ms;

  return (
    <div data-testid="autonomy-screen" className="flex flex-col gap-6">
      {/* Policy-link status */}
      <div className="flex items-center gap-3 rounded-md border border-zinc-700 bg-zinc-900 px-4 py-3">
        <div
          className={`h-2.5 w-2.5 rounded-full ${
            policyConnected ? "bg-green-400" : "bg-zinc-600"
          }`}
        />
        <span className="text-sm text-zinc-300">
          Policy link:{" "}
          {policyConnected == null
            ? "—"
            : policyConnected
              ? "connected"
              : "disconnected"}
          {inferMs != null && ` · ${inferMs.toFixed(1)} ms`}
        </span>
        {stale && (
          <span
            data-testid="stale-banner"
            className="ml-auto rounded bg-yellow-800/60 px-2 py-0.5 text-xs text-yellow-300"
          >
            STALE — drop-to-stop active
          </span>
        )}
      </div>

      {/* Latency chart */}
      {seriesSnap.length > 0 && <PolicyLinkChart samples={seriesSnap} />}

      {/* Task picker */}
      <div className="flex flex-col gap-3 rounded-md border border-zinc-700 bg-zinc-900 p-4">
        <p className="text-sm font-medium text-zinc-300">Task</p>
        <div className="flex gap-2">
          {TASK_KEYS.map((key) => (
            <button
              key={key}
              onClick={() => {
                setSelectedTask(key);
                setCustomPrompt("");
              }}
              className={`rounded px-3 py-1.5 text-sm capitalize ${
                selectedTask === key && !customPrompt
                  ? "bg-zinc-600 text-white"
                  : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
              }`}
            >
              {key}
            </button>
          ))}
        </div>

        <input
          type="text"
          value={customPrompt}
          onChange={(e) => setCustomPrompt(e.target.value)}
          placeholder={TASK_PROMPTS[selectedTask]}
          className="rounded border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-white placeholder:text-zinc-600 focus:border-zinc-500 focus:outline-none"
        />

        {/* max_speed slider */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-zinc-500">
            Max speed: <span className="text-zinc-300">{maxSpeed.toFixed(2)} m/s</span>
          </label>
          <Slider.Root
            className="relative flex h-5 w-full items-center"
            min={0.05}
            max={0.5}
            step={0.05}
            value={[maxSpeed]}
            onValueChange={([v]) => setMaxSpeed(v)}
          >
            <Slider.Track className="relative h-1 grow rounded-full bg-zinc-700">
              <Slider.Range className="absolute h-full rounded-full bg-zinc-400" />
            </Slider.Track>
            <Slider.Thumb className="block h-4 w-4 rounded-full bg-white shadow focus:outline-none" />
          </Slider.Root>
        </div>

        {/* control_hz input */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-zinc-500">Control Hz:</label>
          <input
            type="number"
            value={controlHz}
            onChange={(e) => setControlHz(Number(e.target.value))}
            min={1}
            max={50}
            className="w-20 rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-sm text-white focus:border-zinc-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Controls */}
      <div className="flex gap-3">
        <button
          onClick={handleStart}
          disabled={running || !prompt}
          className="rounded-md bg-green-700 px-5 py-2 text-sm font-medium text-white hover:bg-green-600 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Start
        </button>
        <button
          onClick={handleStop}
          disabled={!running}
          className="rounded-md bg-red-700 px-5 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Stop
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-red-700 bg-red-950/50 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {running && (
        <p data-testid="running-indicator" className="text-sm text-green-400">
          Autonomy running…
        </p>
      )}
    </div>
  );
}
