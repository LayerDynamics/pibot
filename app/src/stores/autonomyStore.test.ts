import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAutonomyStore } from "./autonomyStore";

const FAKE_EP = { url: "http://localhost:9999", token: "test-token" };

beforeEach(() => {
  useAutonomyStore.getState().reset();
  vi.restoreAllMocks();
});

describe("autonomyStore.updateFromSnapshot", () => {
  it("starts with no policy and not stale", () => {
    const s = useAutonomyStore.getState();
    expect(s.policy).toBeNull();
    expect(s.stale).toBe(false);
    expect(s.running).toBe(false);
  });

  it("stores the policy block from the snapshot", () => {
    const policy = { connected: true, last_inference_ms: 42.0, chunk_age_ms: 100.0 };
    useAutonomyStore.getState().updateFromSnapshot(policy);
    expect(useAutonomyStore.getState().policy).toEqual(policy);
  });

  it("sets stale when chunk_age_ms > 1000", () => {
    useAutonomyStore
      .getState()
      .updateFromSnapshot({ connected: true, last_inference_ms: 10.0, chunk_age_ms: 1500.0 });
    expect(useAutonomyStore.getState().stale).toBe(true);
  });

  it("clears stale when chunk_age_ms <= 1000", () => {
    // First make it stale
    useAutonomyStore
      .getState()
      .updateFromSnapshot({ connected: true, last_inference_ms: 10.0, chunk_age_ms: 2000.0 });
    expect(useAutonomyStore.getState().stale).toBe(true);
    // Then clear it
    useAutonomyStore
      .getState()
      .updateFromSnapshot({ connected: true, last_inference_ms: 10.0, chunk_age_ms: 500.0 });
    expect(useAutonomyStore.getState().stale).toBe(false);
  });

  it("is not stale when policy is null", () => {
    useAutonomyStore.getState().updateFromSnapshot(null);
    expect(useAutonomyStore.getState().stale).toBe(false);
  });

  it("is not stale when chunk_age_ms is null", () => {
    useAutonomyStore
      .getState()
      .updateFromSnapshot({ connected: null, last_inference_ms: null, chunk_age_ms: null });
    expect(useAutonomyStore.getState().stale).toBe(false);
  });
});

describe("autonomyStore.start", () => {
  it("sets running on 2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ autonomy: "started" }) }),
    );
    await useAutonomyStore.getState().start(FAKE_EP, "navigate to goal");
    expect(useAutonomyStore.getState().running).toBe(true);
    expect(useAutonomyStore.getState().error).toBeNull();
  });

  it("sends prompt/max_speed/control_hz in the request body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    await useAutonomyStore.getState().start(FAKE_EP, "explore", 0.3, 10.0);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string) as Record<string, unknown>;
    expect(body["prompt"]).toBe("explore");
    expect(body["max_speed"]).toBeCloseTo(0.3);
    expect(body["control_hz"]).toBeCloseTo(10.0);
  });

  it("sets error on non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, text: async () => "not connected" }),
    );
    await useAutonomyStore.getState().start(FAKE_EP, "explore");
    expect(useAutonomyStore.getState().running).toBe(false);
    expect(useAutonomyStore.getState().error).toMatch(/503/);
  });
});

describe("autonomyStore.stop", () => {
  it("clears running on 2xx response", async () => {
    // Manually mark running
    useAutonomyStore.setState({ running: true });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ autonomy: "stopped" }) }),
    );
    await useAutonomyStore.getState().stop(FAKE_EP);
    expect(useAutonomyStore.getState().running).toBe(false);
    expect(useAutonomyStore.getState().error).toBeNull();
  });

  it("sends DELETE to /api/autonomy", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    await useAutonomyStore.getState().stop(FAKE_EP);
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/autonomy");
  });
});
