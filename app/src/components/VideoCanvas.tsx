import { useEffect, useRef } from "react";

import { mcEndpoint, openVideo } from "../lib/api/client";
import { useVideoStore } from "../stores/videoStore";

export default function VideoCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useVideoStore((s) => s.frame);
  const fps = useVideoStore((s) => s.fps);

  // Open the /api/video stream while this view is mounted and feed frames into the store.
  // The sidecar closes the socket immediately when no robot/camera is connected, so this is a
  // no-op until a camera-equipped robot is linked.
  useEffect(() => {
    let ws: WebSocket | null = null;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const { pushFrame, reset } = useVideoStore.getState();
    const open = async (): Promise<void> => {
      if (cancelled) return;
      let ep;
      try {
        ep = await mcEndpoint();
      } catch {
        return; // not in a Tauri context (browser preview / tests) — no video stream
      }
      if (cancelled) return;
      if (!ep.url) {
        // The sidecar hasn't reported its port yet. Retry instead of building a relative
        // (invalid) WebSocket URL, and so the stream opens as soon as the port is known.
        retryTimer = setTimeout(() => void open(), 400);
        return;
      }
      ws = openVideo(ep, (hdr, blob) => void pushFrame(hdr, blob));
    };
    void open();
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
      reset();
    };
  }, []);

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
