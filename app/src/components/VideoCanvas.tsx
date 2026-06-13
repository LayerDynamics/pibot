import { useEffect, useRef } from "react";

import { useVideoStore } from "../stores/videoStore";

export default function VideoCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useVideoStore((s) => s.frame);
  const fps = useVideoStore((s) => s.fps);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !frame?.bitmap) return;
    canvas.width = frame.w;
    canvas.height = frame.h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // Draw via requestAnimationFrame to avoid blocking the control path.
    const raf = requestAnimationFrame(() => {
      ctx.drawImage(frame.bitmap, 0, 0);
    });
    return () => cancelAnimationFrame(raf);
  }, [frame]);

  return (
    <div className="relative w-full" data-testid="video-canvas-container">
      <canvas
        ref={canvasRef}
        className="w-full rounded-md bg-zinc-900"
        data-testid="video-canvas"
      />
      {fps > 0 && (
        <span className="absolute bottom-1 right-2 text-xs text-zinc-400">
          {fps} fps
        </span>
      )}
      {!frame && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-zinc-500">
          No video
        </div>
      )}
    </div>
  );
}
