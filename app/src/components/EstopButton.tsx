import { invoke } from "@tauri-apps/api/core";

import { useConnectionStore } from "../stores/connectionStore";

interface Props {
  epUrl: string;
  token: string;
}

export default function EstopButton({ epUrl, token }: Props) {
  const { estopLatched, setEstopLatched } = useConnectionStore();

  const handleEstop = async () => {
    try {
      await fetch(`${epUrl}/api/estop`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      // Sidecar unreachable — fall back to the Rust failsafe.
      try {
        await invoke("estop_now");
      } catch {
        // Best effort: both paths failed.
      }
    }
    setEstopLatched(true);
  };

  if (estopLatched) {
    return (
      <div data-testid="estop-latched" className="flex items-center gap-2">
        <span className="rounded bg-red-700 px-3 py-1 font-bold text-white">
          E-STOP LATCHED
        </span>
        <button
          type="button"
          className="rounded bg-zinc-700 px-2 py-1 text-sm text-zinc-100 hover:bg-zinc-600"
          onClick={() => setEstopLatched(false)}
          aria-label="Clear e-stop"
        >
          Clear
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      data-testid="estop-button"
      className="rounded bg-red-600 px-4 py-2 font-bold text-white hover:bg-red-500 active:bg-red-700"
      onClick={() => void handleEstop()}
      aria-label="E-Stop"
    >
      E-STOP
    </button>
  );
}
