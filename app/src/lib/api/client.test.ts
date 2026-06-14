import { afterEach, describe, expect, it, vi } from "vitest";

import { openVideo } from "./client";
import type { McEndpoint } from "./types";

// Minimal WebSocket stand-in: openVideo only sets binaryType + onmessage and we drive the
// messages by hand. Capturing the instance lets us replay the sidecar's text-then-binary order.
class FakeWS {
  binaryType = "";
  url: string;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  close = vi.fn();
  constructor(url: string) {
    this.url = url;
  }
}

const EP: McEndpoint = { url: "http://127.0.0.1:5000", token: "tok" };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("openVideo", () => {
  it("pairs each text header with the binary frame that follows it", () => {
    vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
    const frames: Array<[string, Blob]> = [];
    const ws = openVideo(EP, (h, b) => frames.push([h, b])) as unknown as FakeWS;

    // The token rides on the query string and http -> ws scheme conversion happens.
    expect(ws.url).toBe("ws://127.0.0.1:5000/api/video?token=tok");
    expect(ws.binaryType).toBe("blob");

    const header = JSON.stringify({ seq: 1, ts: 1, w: 320, h: 240, fmt: "jpeg" });
    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: "image/jpeg" });
    ws.onmessage?.({ data: header }); // TEXT header
    ws.onmessage?.({ data: blob }); // BINARY jpeg

    expect(frames).toHaveLength(1);
    expect(frames[0][0]).toBe(header);
    expect(frames[0][1]).toBe(blob);
  });

  it("ignores a binary frame that has no preceding header", () => {
    vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket);
    const frames: Array<[string, Blob]> = [];
    const ws = openVideo(EP, (h, b) => frames.push([h, b])) as unknown as FakeWS;

    ws.onmessage?.({ data: new Blob([new Uint8Array([9])]) }); // stray binary, no header
    expect(frames).toHaveLength(0);

    // ...and a header alone (no binary yet) does not emit either.
    ws.onmessage?.({ data: JSON.stringify({ seq: 0 }) });
    expect(frames).toHaveLength(0);
  });
});
