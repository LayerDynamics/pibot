import { create } from "zustand";

export interface VideoFrame {
  seq: number;
  ts: number;
  w: number;
  h: number;
  fmt: string;
  bitmap: ImageBitmap;
}

interface VideoState {
  frame: VideoFrame | null;
  fps: number;
  _timestamps: number[];
  pushFrame: (headerJson: string, blob: Blob) => Promise<void>;
  reset: () => void;
}

export const useVideoStore = create<VideoState>((set, get) => ({
  frame: null,
  fps: 0,
  _timestamps: [],

  pushFrame: async (headerJson: string, blob: Blob) => {
    let header: { seq: number; ts: number; w: number; h: number; fmt: string };
    try {
      header = JSON.parse(headerJson) as typeof header;
    } catch {
      return;
    }

    let bitmap: ImageBitmap;
    try {
      bitmap = await createImageBitmap(blob);
    } catch {
      return;
    }

    // Close the previous bitmap to release GPU memory (drop-oldest).
    const prev = get().frame;
    if (prev?.bitmap) {
      try {
        prev.bitmap.close();
      } catch {
        // ignore
      }
    }

    // Update FPS counter using a 1-second sliding window.
    const now = performance.now();
    const windowMs = 1000;
    const timestamps = [...get()._timestamps, now].filter(
      (t) => now - t < windowMs,
    );
    const fps = timestamps.length;

    set({
      frame: { ...header, bitmap },
      fps,
      _timestamps: timestamps,
    });
  },

  reset: () => {
    const prev = get().frame;
    if (prev?.bitmap) {
      try {
        prev.bitmap.close();
      } catch {
        // ignore
      }
    }
    set({ frame: null, fps: 0, _timestamps: [] });
  },
}));
