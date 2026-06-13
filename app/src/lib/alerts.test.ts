import { describe, expect, it } from "vitest";

import { alerts } from "./alerts";
import type { Snapshot } from "./api/types";

const base: Snapshot = {
  ts: 0,
  pi: { temp_c: 50, cpu_pct: 5, mem_pct: 20, throttled: { currently: [] } },
  robot: { battery: { volts: 12 } },
  transport: { open: true },
  safety: { estop: false },
  policy: { connected: null, last_inference_ms: null, chunk_age_ms: null },
};

describe("alerts (mirrors pibot/monitor.check_thresholds)", () => {
  it("is empty when healthy", () => {
    expect(alerts(base)).toEqual([]);
  });

  it("flags hot SoC at the threshold", () => {
    expect(alerts({ ...base, pi: { ...base.pi, temp_c: 80 } })).toContain("temp 80°C ≥ 80°C");
  });

  it("flags active throttling", () => {
    const snap = { ...base, pi: { ...base.pi, throttled: { currently: ["under-voltage"] } } };
    expect(alerts(snap)).toContain("throttled: under-voltage");
  });

  it("flags low battery", () => {
    expect(alerts({ ...base, robot: { battery: { volts: 10.5 } } })).toContain(
      "battery 10.5V < 11V",
    );
  });

  it("flags transport down", () => {
    expect(alerts({ ...base, transport: { open: false } })).toContain("transport down");
  });

  it("flags a latched e-stop", () => {
    expect(alerts({ ...base, safety: { estop: true } })).toContain("e-stop latched");
  });

  it("flags a down policy link", () => {
    const snap = {
      ...base,
      policy: { connected: false, last_inference_ms: null, chunk_age_ms: null },
    };
    expect(alerts(snap)).toContain("policy down");
  });

  it("flags a stale policy chunk", () => {
    const snap = {
      ...base,
      policy: { connected: true, last_inference_ms: 700, chunk_age_ms: 1500 },
    };
    expect(alerts(snap).some((a) => a.startsWith("policy chunk stale"))).toBe(true);
  });
});
