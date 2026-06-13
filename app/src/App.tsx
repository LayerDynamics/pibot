/**
 * Application shell: a persistent top bar (connection state + always-visible e-stop,
 * SPEC-3 FR-8) and a screen-navigation row wrapping the active screen. Mounts the five
 * operator screens — Dashboard, Drive (teleop), Autonomy, Data & Models, Provisioning —
 * resolves the loopback control-plane endpoint for the e-stop + data/provisioning screens,
 * and starts the native-notification subscription (FR-22).
 */
import { useEffect, useState } from "react";

import ConnectBar from "./components/ConnectBar";
import EstopButton from "./components/EstopButton";
import { mcEndpoint } from "./lib/api/client";
import type { McEndpoint } from "./lib/api/types";
import Autonomy from "./screens/Autonomy";
import Dashboard from "./screens/Dashboard";
import Data from "./screens/Data";
import Drive from "./screens/Drive";
import Provisioning from "./screens/Provisioning";
import { useConnectionStore } from "./stores/connectionStore";
import { useNotifyStore } from "./stores/notifyStore";

type ScreenKey = "dashboard" | "drive" | "autonomy" | "data" | "provisioning";

const SCREENS: Array<{ key: ScreenKey; label: string }> = [
  { key: "dashboard", label: "Dashboard" },
  { key: "drive", label: "Drive" },
  { key: "autonomy", label: "Autonomy" },
  { key: "data", label: "Data" },
  { key: "provisioning", label: "Provisioning" },
];

function connectionLabel(state: string, robot: string | null): string {
  if (state === "connected") {
    return robot ? `Connected: ${robot}` : "Connected";
  }
  if (state === "connecting") {
    return "Connecting…";
  }
  return "Disconnected";
}

export default function App() {
  const state = useConnectionStore((s) => s.state);
  const robot = useConnectionStore((s) => s.robot);
  const connected = state === "connected";

  const [screen, setScreen] = useState<ScreenKey>("dashboard");
  const [ep, setEp] = useState<McEndpoint | null>(null);

  // Resolve the loopback control-plane endpoint + per-launch token once. Used by the
  // always-on e-stop (with a Rust failsafe fallback) and the data/provisioning screens.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const resolved = await mcEndpoint();
        if (!cancelled) {
          setEp(resolved);
        }
      } catch {
        // Not in a Tauri context (unit test / browser preview). The Rust e-stop
        // failsafe still works via the endpoint cached from the sidecar's stdout.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Raise OS notifications for new telemetry alerts (focus-gated + debounced, FR-22).
  useEffect(() => useNotifyStore.getState().start(), []);

  return (
    <div className="flex h-screen flex-col bg-zinc-950 text-zinc-100">
      <header
        data-testid="top-bar"
        className="flex items-center justify-between border-b border-zinc-800 px-4 py-2"
      >
        <div className="flex items-center gap-3">
          <span className="font-semibold tracking-tight">PiBot Mission Control</span>
          <span
            data-testid="connection-indicator"
            className={`rounded-full px-2 py-0.5 text-xs ${
              connected ? "bg-emerald-900 text-emerald-300" : "bg-zinc-800 text-zinc-400"
            }`}
          >
            {connectionLabel(state, robot)}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <ConnectBar />
          <EstopButton epUrl={ep?.url ?? ""} token={ep?.token ?? ""} />
        </div>
      </header>

      <nav
        data-testid="screen-nav"
        className="flex items-center gap-1 border-b border-zinc-800 px-4 py-1.5"
      >
        {SCREENS.map((s) => (
          <button
            key={s.key}
            type="button"
            onClick={() => setScreen(s.key)}
            aria-current={screen === s.key ? "page" : undefined}
            className={`rounded px-3 py-1 text-sm ${
              screen === s.key
                ? "bg-zinc-700 text-white"
                : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
            }`}
          >
            {s.label}
          </button>
        ))}
      </nav>

      <main data-testid="screen-region" className="flex-1 overflow-auto p-4">
        {screen === "dashboard" && <Dashboard />}
        {screen === "drive" && <Drive />}
        {screen === "autonomy" && <Autonomy />}
        {screen === "data" && <Data ep={ep} />}
        {screen === "provisioning" && <Provisioning ep={ep} />}
      </main>
    </div>
  );
}
