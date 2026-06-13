import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { Snapshot } from "../lib/api/types";
import { clearDebounce, resetSendFn, setSendFn } from "../lib/notify";
import { useNotifyStore } from "./notifyStore";
import { useTelemetryStore } from "./telemetryStore";

function mockFocus(focused: boolean) {
  Object.defineProperty(document, "hasFocus", {
    writable: true,
    configurable: true,
    value: () => focused,
  });
}

/** A telemetry snapshot; `estop=true` yields the "e-stop latched" alert. */
function snapshot(estop: boolean): Snapshot {
  return {
    ts: 1,
    pi: {},
    robot: {},
    transport: { open: true },
    safety: { estop },
    policy: { connected: null, last_inference_ms: null, chunk_age_ms: null },
  };
}

let sent: Array<{ title: string; body: string }>;
let unsub: () => void;

beforeEach(() => {
  sent = [];
  clearDebounce();
  setSendFn((title, body) => {
    sent.push({ title, body });
  });
  useTelemetryStore.getState().clear();
  useNotifyStore.getState().setEnabled(true);
  unsub = useNotifyStore.getState().start();
});

afterEach(() => {
  unsub();
  resetSendFn();
  useTelemetryStore.getState().clear();
});

describe("notifyStore — telemetry alerts -> OS notifications", () => {
  it("raises a notification when a new telemetry alert appears (unfocused)", () => {
    mockFocus(false);
    useTelemetryStore.getState().setSnapshot(snapshot(true));
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toBe("e-stop latched");
    expect(sent[0].title).toBe("PiBot Alert");
  });

  it("does not notify while the window is focused", () => {
    mockFocus(true);
    useTelemetryStore.getState().setSnapshot(snapshot(true));
    expect(sent).toHaveLength(0);
  });

  it("does not notify when disabled", () => {
    mockFocus(false);
    useNotifyStore.getState().setEnabled(false);
    useTelemetryStore.getState().setSnapshot(snapshot(true));
    expect(sent).toHaveLength(0);
  });

  it("does not notify when a snapshot carries no alerts", () => {
    mockFocus(false);
    useTelemetryStore.getState().setSnapshot(snapshot(false));
    expect(sent).toHaveLength(0);
  });
});
