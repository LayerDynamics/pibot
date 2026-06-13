import { useEffect, useRef, useState } from "react";

import {
  connectRobot,
  disconnectRobot,
  listRobots,
  mcEndpoint,
  openTelemetry,
} from "../lib/api/client";
import type { RobotEntry } from "../lib/api/types";
import { useConnectionStore } from "../stores/connectionStore";
import { useTelemetryStore } from "../stores/telemetryStore";

export default function ConnectBar() {
  const [robots, setRobots] = useState<RobotEntry[]>([]);
  const [selected, setSelected] = useState("");
  const conn = useConnectionStore((s) => s.state);
  const setConn = useConnectionStore((s) => s.setState);
  const setError = useConnectionStore((s) => s.setError);
  const setSnapshot = useTelemetryStore((s) => s.setSnapshot);
  const clearTelemetry = useTelemetryStore((s) => s.clear);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const ep = await mcEndpoint();
        const list = await listRobots(ep);
        setRobots(list);
        if (list.length > 0) {
          setSelected(list[0].alias);
        }
      } catch (e) {
        setError(String(e));
      }
    })();
  }, [setError]);

  async function onConnect() {
    if (!selected) {
      return;
    }
    setConn("connecting");
    try {
      const ep = await mcEndpoint();
      await connectRobot(ep, selected);
      wsRef.current = openTelemetry(ep, setSnapshot);
      setConn("connected", selected);
    } catch (e) {
      setError(String(e));
    }
  }

  async function onDisconnect() {
    wsRef.current?.close();
    wsRef.current = null;
    clearTelemetry();
    try {
      const ep = await mcEndpoint();
      await disconnectRobot(ep);
    } finally {
      setConn("disconnected");
    }
  }

  return (
    <div className="flex items-center gap-2">
      <select
        aria-label="robot"
        className="rounded bg-zinc-800 px-2 py-1 text-sm"
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        disabled={conn === "connected"}
      >
        {robots.length === 0 && <option value="">no robots</option>}
        {robots.map((r) => (
          <option key={r.alias} value={r.alias}>
            {r.alias} ({r.address})
          </option>
        ))}
      </select>
      {conn === "connected" ? (
        <button
          type="button"
          onClick={() => void onDisconnect()}
          className="rounded bg-zinc-700 px-3 py-1 text-sm"
        >
          Disconnect
        </button>
      ) : (
        <button
          type="button"
          onClick={() => void onConnect()}
          disabled={!selected || conn === "connecting"}
          className="rounded bg-emerald-600 px-3 py-1 text-sm font-medium disabled:opacity-50"
        >
          {conn === "connecting" ? "Connecting…" : "Connect"}
        </button>
      )}
    </div>
  );
}
