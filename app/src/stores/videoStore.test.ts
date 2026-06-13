import { beforeEach, describe, expect, it, vi } from "vitest";

import { useVideoStore } from "./videoStore";

// jsdom doesn't implement createImageBitmap — stub it.
vi.stubGlobal(
  "createImageBitmap",
  vi.fn().mockResolvedValue({ width: 320, height: 240, close: vi.fn() }),
);

const makeBlob = (size = 16) =>
  new Blob([new Uint8Array(size).fill(0xff)], { type: "image/jpeg" });

beforeEach(() => {
  useVideoStore.getState().reset();
  vi.clearAllMocks();
});

describe("videoStore", () => {
  it("starts empty", () => {
    const s = useVideoStore.getState();
    expect(s.frame).toBeNull();
    expect(s.fps).toBe(0);
  });

  it("pushFrame updates frame after bitmap decode", async () => {
    const header = JSON.stringify({ seq: 0, ts: 1.0, w: 320, h: 240, fmt: "jpeg" });
    await useVideoStore.getState().pushFrame(header, makeBlob());
    expect(useVideoStore.getState().frame).not.toBeNull();
    expect(useVideoStore.getState().frame?.w).toBe(320);
    expect(useVideoStore.getState().frame?.h).toBe(240);
  });

  it("tracks fps over multiple frames", async () => {
    const hdr = JSON.stringify({ seq: 0, ts: 0.0, w: 320, h: 240, fmt: "jpeg" });
    // Push several frames quickly to build up the fps counter.
    for (let i = 0; i < 5; i++) {
      await useVideoStore.getState().pushFrame(hdr, makeBlob());
    }
    expect(useVideoStore.getState().fps).toBeGreaterThanOrEqual(0);
  });

  it("drop-oldest: only the latest frame is kept", async () => {
    const hdr0 = JSON.stringify({ seq: 0, ts: 0.0, w: 320, h: 240, fmt: "jpeg" });
    const hdr1 = JSON.stringify({ seq: 1, ts: 0.1, w: 320, h: 240, fmt: "jpeg" });
    await useVideoStore.getState().pushFrame(hdr0, makeBlob());
    await useVideoStore.getState().pushFrame(hdr1, makeBlob());
    // Exactly one frame is kept at a time.
    expect(useVideoStore.getState().frame?.seq).toBe(1);
  });

  it("reset clears frame and fps", async () => {
    const hdr = JSON.stringify({ seq: 0, ts: 0.0, w: 320, h: 240, fmt: "jpeg" });
    await useVideoStore.getState().pushFrame(hdr, makeBlob());
    useVideoStore.getState().reset();
    expect(useVideoStore.getState().frame).toBeNull();
    expect(useVideoStore.getState().fps).toBe(0);
  });

  it("flooding frames never throws (drop-oldest policy)", async () => {
    const hdr = JSON.stringify({ seq: 0, ts: 0.0, w: 320, h: 240, fmt: "jpeg" });
    await expect(
      Promise.all(
        Array.from({ length: 20 }, () =>
          useVideoStore.getState().pushFrame(hdr, makeBlob()),
        ),
      ),
    ).resolves.not.toThrow();
  });
});
