import { useEffect, useRef } from "react";

import VideoCanvas from "../components/VideoCanvas";
import { useGamepadStore } from "../stores/gamepadStore";
import { useTeleopStore } from "../stores/teleopStore";

export default function Drive() {
  const { keyDown, keyUp, stop, pressedKeys } = useTeleopStore();
  const { start: gpStart, stop: gpStop } = useGamepadStore();
  const containerRef = useRef<HTMLDivElement>(null);

  // Start the gamepad poll loop while the Drive screen is mounted.
  useEffect(() => {
    gpStart();
    return () => gpStop();
  }, [gpStart, gpStop]);

  // Capture keyboard events when the Drive screen is mounted.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Prevent page scroll on arrow keys.
      if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", " "].includes(e.key)) {
        e.preventDefault();
      }
      keyDown(e.code);
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      keyUp(e.code);
    };
    const handleBlur = () => {
      stop();
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", handleBlur);

    return () => {
      stop();
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", handleBlur);
    };
  }, [keyDown, keyUp, stop]);

  const moving = pressedKeys.size > 0;

  return (
    <div
      ref={containerRef}
      data-testid="drive-screen"
      className="flex flex-col items-center gap-6"
    >
      <VideoCanvas />
      <div className="rounded-md border border-zinc-700 bg-zinc-900 px-6 py-4 text-center">
        <p className="mb-2 text-sm text-zinc-400">
          {moving ? "Driving…" : "Use W/A/S/D or arrow keys to drive. Escape to stop."}
        </p>
        <div className="grid grid-cols-3 gap-2 text-center text-xs text-zinc-500">
          <div />
          <div
            className={`rounded px-2 py-1 ${pressedKeys.has("KeyW") || pressedKeys.has("ArrowUp") ? "bg-zinc-600 text-white" : "bg-zinc-800"}`}
          >
            W ▲
          </div>
          <div />
          <div
            className={`rounded px-2 py-1 ${pressedKeys.has("KeyA") || pressedKeys.has("ArrowLeft") ? "bg-zinc-600 text-white" : "bg-zinc-800"}`}
          >
            A ◀
          </div>
          <div
            className={`rounded px-2 py-1 ${pressedKeys.has("KeyS") || pressedKeys.has("ArrowDown") ? "bg-zinc-600 text-white" : "bg-zinc-800"}`}
          >
            S ▼
          </div>
          <div
            className={`rounded px-2 py-1 ${pressedKeys.has("KeyD") || pressedKeys.has("ArrowRight") ? "bg-zinc-600 text-white" : "bg-zinc-800"}`}
          >
            D ▶
          </div>
        </div>
      </div>
    </div>
  );
}
