import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import type { Snapshot } from "../lib/api/types";
import { useTelemetryStore } from "../stores/telemetryStore";
import Dashboard from "./Dashboard";

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

describe("Dashboard", () => {
  it("shows the empty state with no telemetry", () => {
    render(<Dashboard />);
    expect(screen.getByTestId("dashboard-empty")).toBeInTheDocument();
  });

  it("renders telemetry values once a snapshot arrives", () => {
    useTelemetryStore.getState().setSnapshot(SNAP);
    render(<Dashboard />);
    expect(screen.getByTestId("dashboard")).toBeInTheDocument();
    expect(screen.getByText("61°C")).toBeInTheDocument();
    expect(screen.getByText("12.1V")).toBeInTheDocument();
  });

  it("surfaces threshold alerts", () => {
    useTelemetryStore.getState().setSnapshot({ ...SNAP, safety: { estop: true } });
    render(<Dashboard />);
    expect(screen.getByTestId("alerts")).toHaveTextContent("e-stop latched");
  });
});
