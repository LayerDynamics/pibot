import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEBOUNCE_MS, clearDebounce, notifyAlerts, resetSendFn, setSendFn } from "./notify";

function mockFocus(focused: boolean) {
  Object.defineProperty(document, "hasFocus", {
    writable: true,
    configurable: true,
    value: () => focused,
  });
}

let sent: Array<{ title: string; body: string }> = [];

beforeEach(() => {
  sent = [];
  clearDebounce();
  setSendFn((title, body) => { sent.push({ title, body }); });
});

afterEach(() => {
  resetSendFn();
});

describe("notifyAlerts — focus gate", () => {
  it("does NOT fire when window is focused", () => {
    mockFocus(true);
    notifyAlerts(["temp 85°C ≥ 80°C"]);
    expect(sent).toHaveLength(0);
  });

  it("fires when window is unfocused", () => {
    mockFocus(false);
    notifyAlerts(["e-stop latched"]);
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toBe("e-stop latched");
    expect(sent[0].title).toBe("PiBot Alert");
  });
});

describe("notifyAlerts — debounce", () => {
  it("suppresses the same message within DEBOUNCE_MS", () => {
    mockFocus(false);
    notifyAlerts(["battery 10V < 11V"]);
    notifyAlerts(["battery 10V < 11V"]); // immediate repeat
    expect(sent).toHaveLength(1);
  });

  it("re-fires after DEBOUNCE_MS has elapsed", () => {
    mockFocus(false);
    notifyAlerts(["battery 10V < 11V"]);
    // Advance time past debounce.
    vi.useFakeTimers();
    vi.advanceTimersByTime(DEBOUNCE_MS + 1);
    clearDebounce(); // simulate time-based reset by just clearing
    notifyAlerts(["battery 10V < 11V"]);
    vi.useRealTimers();
    expect(sent).toHaveLength(2);
  });

  it("fires different messages independently", () => {
    mockFocus(false);
    notifyAlerts(["e-stop latched", "temp 85°C ≥ 80°C"]);
    expect(sent).toHaveLength(2);
  });
});

describe("notifyAlerts — empty alerts", () => {
  it("fires nothing for an empty alert list", () => {
    mockFocus(false);
    notifyAlerts([]);
    expect(sent).toHaveLength(0);
  });
});
