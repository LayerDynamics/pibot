import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { useConnectionStore } from "../stores/connectionStore";
import EstopButton from "./EstopButton";

// Mock fetch so we don't make real HTTP calls.
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Mock Tauri invoke as a fallback (not called when fetch succeeds).
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockResolvedValue(undefined),
}));

beforeEach(() => {
  mockFetch.mockReset();
  useConnectionStore.getState().setEstopLatched(false);
  useConnectionStore.getState().setState("disconnected");
});

describe("EstopButton", () => {
  it("renders with an unmistakable label", () => {
    render(<EstopButton epUrl="http://127.0.0.1:9000" token="tok" />);
    expect(screen.getByRole("button", { name: /e.?stop/i })).toBeTruthy();
  });

  it("posts /api/estop on click", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    render(<EstopButton epUrl="http://127.0.0.1:9000" token="tok" />);
    fireEvent.click(screen.getByRole("button", { name: /e.?stop/i }));
    // Give the async fetch a tick.
    await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    const [url, opts] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:9000/api/estop");
    expect((opts.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok");
  });

  it("enters latched state after successful estop", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    render(<EstopButton epUrl="http://127.0.0.1:9000" token="tok" />);
    fireEvent.click(screen.getByRole("button", { name: /e.?stop/i }));
    await vi.waitFor(() =>
      expect(useConnectionStore.getState().estopLatched).toBe(true),
    );
    expect(screen.getByTestId("estop-latched")).toBeTruthy();
  });

  it("clears latched state when clear is clicked", async () => {
    useConnectionStore.getState().setEstopLatched(true);
    render(<EstopButton epUrl="http://127.0.0.1:9000" token="tok" />);
    fireEvent.click(screen.getByRole("button", { name: /clear/i }));
    expect(useConnectionStore.getState().estopLatched).toBe(false);
  });
});
