/**
 * ROS panel: a native ROS 2 view of the robot via rosbridge (port 9090 over Nebula). It
 * connects with roslib, shows the topics `pibot.ros2.bridge` publishes — e-stop state,
 * telemetry, and the camera (`/pibot/image/compressed`) — and drives the robot by publishing
 * `/cmd_vel` (press-and-hold; the bridge's deadman stops the robot when you release). The
 * default rosbridge URL is derived from the connected robot's inventory address.
 */
import { useEffect, useRef, useState } from "react";

import { listRobots, mcEndpoint } from "../lib/api/client";
import type { Snapshot } from "../lib/api/types";
import { RosLink, rosbridgeUrl, type RosStatus } from "../lib/ros/rosClient";
import { useConnectionStore } from "../stores/connectionStore";

const STATUS_STYLE: Record<RosStatus, string> = {
  idle: "bg-zinc-800 text-zinc-400",
  connecting: "bg-amber-900 text-amber-300",
  connected: "bg-emerald-900 text-emerald-300",
  error: "bg-red-900 text-red-300",
  closed: "bg-zinc-800 text-zinc-400",
};

export default function Ros() {
  const robotAlias = useConnectionStore((s) => s.robot);
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<RosStatus>("idle");
  const [estop, setEstop] = useState<boolean | null>(null);
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [speed, setSpeed] = useState(0.3);
  const linkRef = useRef<RosLink | null>(null);
  const driveTimer = useRef<number | null>(null);

  // Default the rosbridge URL from the connected robot's address (else the first Pi robot).
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const ep = await mcEndpoint();
        const robots = await listRobots(ep);
        const entry = robots.find((r) => r.alias === robotAlias) ?? robots.find((r) => r.pi);
        if (!cancelled && entry) {
          setUrl((current) => current || rosbridgeUrl(entry.address));
        }
      } catch {
        // Not in a Tauri/sidecar context — the operator types the URL by hand.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [robotAlias]);

  function stopDrive(): void {
    if (driveTimer.current !== null) {
      window.clearInterval(driveTimer.current);
      driveTimer.current = null;
    }
    linkRef.current?.drive(0, 0);
  }

  function startDrive(linear: number, angular: number): void {
    stopDrive();
    const send = () => linkRef.current?.drive(linear, angular);
    send();
    driveTimer.current = window.setInterval(send, 100); // 10 Hz while held
  }

  // Tear down the link + any held drive on unmount.
  useEffect(() => {
    return () => {
      stopDrive();
      linkRef.current?.close();
      linkRef.current = null;
    };
  }, []);

  function toggleConnect(): void {
    if (status === "connected" || status === "connecting") {
      stopDrive();
      linkRef.current?.close();
      linkRef.current = null;
      setStatus("closed");
      return;
    }
    const link = new RosLink();
    linkRef.current = link;
    link.connect(url, {
      onStatus: setStatus,
      onEstop: setEstop,
      onTelemetry: setSnap,
      onImageJpegBase64: setImage,
    });
  }

  const connected = status === "connected";
  const driveBtn =
    "select-none rounded bg-zinc-800 px-4 py-3 text-lg hover:bg-zinc-700 active:bg-emerald-700 disabled:opacity-40";

  return (
    <div data-testid="ros-screen" className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <input
          aria-label="rosbridge url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="ws://<robot>:9090"
          disabled={connected}
          className="w-72 rounded bg-zinc-800 px-2 py-1 font-mono text-sm"
        />
        <button
          type="button"
          onClick={toggleConnect}
          disabled={!url}
          className="rounded bg-emerald-600 px-3 py-1 text-sm font-medium disabled:opacity-50"
        >
          {connected ? "Disconnect" : status === "connecting" ? "Connecting…" : "Connect"}
        </button>
        <span
          data-testid="ros-status"
          className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLE[status]}`}
        >
          rosbridge: {status}
        </span>
        <span
          data-testid="ros-estop"
          className={`rounded-full px-2 py-0.5 text-xs ${
            estop ? "bg-red-900 text-red-300" : "bg-zinc-800 text-zinc-400"
          }`}
        >
          e-stop: {estop === null ? "—" : estop ? "LATCHED" : "clear"}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="rounded border border-zinc-800 p-3">
          <h2 className="mb-2 text-sm font-semibold text-zinc-300">/pibot/image/compressed</h2>
          {image ? (
            <img
              data-testid="ros-image"
              alt="robot camera (ROS)"
              src={`data:image/jpeg;base64,${image}`}
              className="w-full rounded bg-black object-contain"
            />
          ) : (
            <div className="flex h-40 items-center justify-center text-sm text-zinc-500">
              {connected ? "waiting for frames…" : "connect to view the camera"}
            </div>
          )}
        </section>

        <section className="rounded border border-zinc-800 p-3">
          <h2 className="mb-2 text-sm font-semibold text-zinc-300">/pibot/telemetry</h2>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-zinc-500">SoC temp</dt>
            <dd>{snap?.pi.temp_c == null ? "—" : `${snap.pi.temp_c.toFixed(1)} °C`}</dd>
            <dt className="text-zinc-500">CPU</dt>
            <dd>{snap?.pi.cpu_pct == null ? "—" : `${snap.pi.cpu_pct.toFixed(0)} %`}</dd>
            <dt className="text-zinc-500">Memory</dt>
            <dd>{snap?.pi.mem_pct == null ? "—" : `${snap.pi.mem_pct.toFixed(0)} %`}</dd>
            <dt className="text-zinc-500">Transport</dt>
            <dd>{snap?.transport.kind ?? snap?.transport.backend ?? "—"}</dd>
          </dl>

          <h2 className="mt-4 mb-2 text-sm font-semibold text-zinc-300">/cmd_vel (hold to drive)</h2>
          <div className="grid w-44 grid-cols-3 gap-1">
            <span />
            <button
              type="button"
              aria-label="forward"
              disabled={!connected}
              onPointerDown={() => startDrive(speed, 0)}
              onPointerUp={stopDrive}
              onPointerLeave={stopDrive}
              className={driveBtn}
            >
              ↑
            </button>
            <span />
            <button
              type="button"
              aria-label="left"
              disabled={!connected}
              onPointerDown={() => startDrive(0, speed * 2)}
              onPointerUp={stopDrive}
              onPointerLeave={stopDrive}
              className={driveBtn}
            >
              ←
            </button>
            <button
              type="button"
              aria-label="stop"
              disabled={!connected}
              onClick={stopDrive}
              className="select-none rounded bg-red-800 px-4 py-3 text-lg hover:bg-red-700 disabled:opacity-40"
            >
              ■
            </button>
            <button
              type="button"
              aria-label="right"
              disabled={!connected}
              onPointerDown={() => startDrive(0, -speed * 2)}
              onPointerUp={stopDrive}
              onPointerLeave={stopDrive}
              className={driveBtn}
            >
              →
            </button>
            <span />
            <button
              type="button"
              aria-label="back"
              disabled={!connected}
              onPointerDown={() => startDrive(-speed, 0)}
              onPointerUp={stopDrive}
              onPointerLeave={stopDrive}
              className={driveBtn}
            >
              ↓
            </button>
            <span />
          </div>
          <label className="mt-3 flex items-center gap-2 text-xs text-zinc-500">
            speed
            <input
              aria-label="speed"
              type="range"
              min={0.1}
              max={1.0}
              step={0.1}
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            />
            <span className="font-mono text-zinc-300">{speed.toFixed(1)}</span>
          </label>
        </section>
      </div>
    </div>
  );
}
