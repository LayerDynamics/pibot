import { beforeEach, describe, expect, it, vi } from "vitest";

import type { McEndpoint, TelemetryRow } from "../lib/api/types";
import { useMetricsStore } from "./metricsStore";

const EP: McEndpoint = { url: "http://mc", token: "tok" };

const ROWS: TelemetryRow[] = [
  {
    ts: 1000,
    temp_c: 45.0,
    battery_v: 3.7,
    estop: 0,
    transport_open: 1,
    policy_connected: 1,
    last_infer_ms: 12.5,
    chunk_age_ms: 30.0,
  },
  {
    ts: 1001,
    temp_c: 46.0,
    battery_v: 3.6,
    estop: 0,
    transport_open: 1,
    policy_connected: 1,
    last_infer_ms: 13.0,
    chunk_age_ms: 35.0,
  },
];

beforeEach(() => {
  useMetricsStore.setState({ rows: [], loading: false, error: null });
  vi.restoreAllMocks();
});

describe("fetchHistory", () => {
  it("populates rows from /api/telemetry/history", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ rows: ROWS, count: ROWS.length }),
        }),
      ),
    );
    await useMetricsStore.getState().fetchHistory(EP, { from: 999, to: 1002 });
    expect(useMetricsStore.getState().rows).toHaveLength(2);
    expect(useMetricsStore.getState().rows[0].ts).toBe(1000);
  });

  it("passes from/to as query params", async () => {
    let capturedUrl = "";
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        capturedUrl = url;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ rows: [] }),
        });
      }),
    );
    await useMetricsStore.getState().fetchHistory(EP, { from: 100, to: 200 });
    expect(capturedUrl).toContain("from=100");
    expect(capturedUrl).toContain("to=200");
  });

  it("passes fields param when provided", async () => {
    let capturedUrl = "";
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        capturedUrl = url;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ rows: [] }) });
      }),
    );
    await useMetricsStore
      .getState()
      .fetchHistory(EP, { from: 0, to: 9999, fields: ["ts", "temp_c"] });
    expect(capturedUrl).toContain("fields=ts%2Ctemp_c");
  });

  it("sets error on failure and clears rows", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: 400 })),
    );
    await useMetricsStore.getState().fetchHistory(EP, { from: 0, to: 1 });
    expect(useMetricsStore.getState().error).toBeTruthy();
  });
});

describe("exportData", () => {
  it("returns text from /api/telemetry/export", async () => {
    const CSV = "ts,temp_c\n1000,45.0\n";
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 200, text: () => Promise.resolve(CSV) }),
      ),
    );
    const result = await useMetricsStore.getState().exportData(EP, { from: 0, to: 9999 }, "csv");
    expect(result).toBe(CSV);
  });
});

describe("clear", () => {
  it("resets rows and error", async () => {
    useMetricsStore.setState({ rows: ROWS, error: "prev error" });
    useMetricsStore.getState().clear();
    expect(useMetricsStore.getState().rows).toHaveLength(0);
    expect(useMetricsStore.getState().error).toBeNull();
  });
});
