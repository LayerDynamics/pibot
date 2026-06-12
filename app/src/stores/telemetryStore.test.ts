import { beforeEach, describe, expect, it } from "vitest";

import type { Snapshot } from "../lib/api/types";
import { useTelemetryStore } from "./telemetryStore";

const SNAP: Snapshot = {
  ts: 1,
  pi: { temp_c: 61, cpu_pct: 12, mem_pct: 30, throttled: { currently: [] } },
  robot: { battery: { volts: 12.1 } },
  transport: { open: true },
  safety: { estop: false },
  policy: { connected: null, last_inference_ms: null, chunk_age_ms: null },
};

beforeEach(() => {
  useTelemetryStore.getState().clear();
});

describe("telemetryStore", () => {
  it("reduces a snapshot and exposes the latest values", () => {
    useTelemetryStore.getState().setSnapshot(SNAP);
    expect(useTelemetryStore.getState().snapshot?.pi.temp_c).toBe(61);
    expect(useTelemetryStore.getState().alerts).toEqual([]);
  });

  it("derives alerts from the snapshot", () => {
    useTelemetryStore.getState().setSnapshot({
      ...SNAP,
      pi: { ...SNAP.pi, temp_c: 85 },
      safety: { estop: true },
    });
    const a = useTelemetryStore.getState().alerts;
    expect(a).toContain("e-stop latched");
    expect(a.some((x) => x.startsWith("temp 85"))).toBe(true);
  });

  it("clears back to empty", () => {
    useTelemetryStore.getState().setSnapshot(SNAP);
    useTelemetryStore.getState().clear();
    expect(useTelemetryStore.getState().snapshot).toBeNull();
    expect(useTelemetryStore.getState().alerts).toEqual([]);
  });
});
