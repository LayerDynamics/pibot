import { beforeEach, describe, expect, it, vi } from "vitest";

import { usePolicyServerStore } from "./policyServerStore";

const FAKE_EP = { url: "http://localhost:9999", token: "test-token" };

const RUNNING_INFO = {
  host: "127.0.0.1",
  port: 8000,
  pid: 12345,
  checkpoint: "/ckpt/v1",
  state: "running" as const,
  last_infer_ms: 35.0,
};

const STOPPED_INFO = {
  host: "127.0.0.1",
  port: 8000,
  pid: null,
  checkpoint: null,
  state: "stopped" as const,
  last_infer_ms: null,
};

beforeEach(() => {
  usePolicyServerStore.getState().reset();
  vi.restoreAllMocks();
});

describe("policyServerStore initial state", () => {
  it("starts stopped with no checkpoint", () => {
    const s = usePolicyServerStore.getState();
    expect(s.state).toBe("stopped");
    expect(s.pid).toBeNull();
    expect(s.checkpoint).toBeNull();
    expect(s.last_infer_ms).toBeNull();
    expect(s.error).toBeNull();
  });
});

describe("policyServerStore.start", () => {
  it("posts checkpoint and updates to running state", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => RUNNING_INFO });
    vi.stubGlobal("fetch", fetchMock);

    await usePolicyServerStore.getState().start(FAKE_EP, "/ckpt/v1");

    const s = usePolicyServerStore.getState();
    expect(s.state).toBe("running");
    expect(s.pid).toBe(12345);
    expect(s.checkpoint).toBe("/ckpt/v1");
    expect(s.last_infer_ms).toBeCloseTo(35.0);
    expect(s.error).toBeNull();
  });

  it("sends POST to /api/policy-server with the checkpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => RUNNING_INFO });
    vi.stubGlobal("fetch", fetchMock);

    await usePolicyServerStore.getState().start(FAKE_EP, "/ckpt/v2");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/policy-server");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string) as Record<string, unknown>;
    expect(body["checkpoint"]).toBe("/ckpt/v2");
  });

  it("sets error on network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network error")));
    await usePolicyServerStore.getState().start(FAKE_EP, "/ckpt");
    expect(usePolicyServerStore.getState().error).toMatch(/network error/);
  });
});

describe("policyServerStore.stop", () => {
  it("sends DELETE and transitions to stopped", async () => {
    usePolicyServerStore.setState({ ...RUNNING_INFO, error: null });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => STOPPED_INFO });
    vi.stubGlobal("fetch", fetchMock);

    await usePolicyServerStore.getState().stop(FAKE_EP);

    const s = usePolicyServerStore.getState();
    expect(s.state).toBe("stopped");
    expect(s.pid).toBeNull();

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("DELETE");
  });
});

describe("policyServerStore.refresh", () => {
  it("updates state from GET /api/policy-server", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => RUNNING_INFO });
    vi.stubGlobal("fetch", fetchMock);

    await usePolicyServerStore.getState().refresh(FAKE_EP);

    expect(usePolicyServerStore.getState().state).toBe("running");
    expect(usePolicyServerStore.getState().last_infer_ms).toBeCloseTo(35.0);
  });

  it("is best-effort: silently ignores network errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("gone")));
    // Should not throw
    await expect(usePolicyServerStore.getState().refresh(FAKE_EP)).resolves.not.toThrow();
  });
});
