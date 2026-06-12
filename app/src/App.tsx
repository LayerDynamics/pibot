/**
 * Application shell: the persistent top bar (connection state + always-visible
 * e-stop, SPEC-3 FR-8) wrapping the active screen region. The Dashboard mounts into
 * `screen-region`; later milestones add the Drive/Autonomy/Data/Provisioning screens.
 */
import ConnectBar from "./components/ConnectBar";
import Dashboard from "./screens/Dashboard";
import { useConnectionStore } from "./stores/connectionStore";

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
          <button
            type="button"
            aria-label="E-Stop"
            className="rounded-md bg-red-600 px-4 py-1.5 text-sm font-bold uppercase tracking-wide text-white hover:bg-red-500 focus:outline-none focus:ring-2 focus:ring-red-400"
          >
            E-Stop
          </button>
        </div>
      </header>
      <main data-testid="screen-region" className="flex-1 overflow-auto p-4">
        <Dashboard />
      </main>
    </div>
  );
}
