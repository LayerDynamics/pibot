import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Episode, FineTuneRun } from "../lib/api/types";
import { useDataStore } from "./dataStore";

const EP: McEndpoint = { url: "http://mc", token: "tok" };

// Need the type for inference
import type { McEndpoint } from "../lib/api/types";

const EPISODES: Episode[] = [
  { id: "ep_000000", task: "pick up", length: 5, started: 1000, ended: 1005 },
  { id: "ep_000001", task: "follow me", length: 3, started: 1010, ended: 1013 },
];

const RUNS: FineTuneRun[] = [
  { id: "run-1", dataset: "/tmp/ds", status: "done", checkpoint_out: "/tmp/ckpt", served: false },
];

function mockFetch(responses: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const key = Object.keys(responses).find((k) => url.includes(k));
      const body = key ? responses[key] : {};
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(body),
        text: () => Promise.resolve(JSON.stringify(body)),
      });
    }),
  );
}

beforeEach(() => {
  useDataStore.setState({ episodes: [], runs: [], loading: false, error: null });
  vi.restoreAllMocks();
});

describe("fetchEpisodes", () => {
  it("populates episodes from /api/episodes", async () => {
    mockFetch({ "/api/episodes": { episodes: EPISODES } });
    await useDataStore.getState().fetchEpisodes(EP);
    expect(useDataStore.getState().episodes).toEqual(EPISODES);
    expect(useDataStore.getState().loading).toBe(false);
  });

  it("sets error on fetch failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) }),
      ),
    );
    await useDataStore.getState().fetchEpisodes(EP);
    expect(useDataStore.getState().error).toBeTruthy();
    expect(useDataStore.getState().episodes).toEqual([]);
  });
});

describe("fetchRuns", () => {
  it("populates runs from /api/finetune", async () => {
    mockFetch({ "/api/finetune": { runs: RUNS } });
    await useDataStore.getState().fetchRuns(EP);
    expect(useDataStore.getState().runs).toEqual(RUNS);
  });
});

describe("serveCheckpoint", () => {
  it("posts to /serve and refreshes runs", async () => {
    const servedRun = { ...RUNS[0], served: true };
    const fetchMock = vi.fn((url: string) => {
      if (url.includes("/serve")) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ serving: true }) });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ runs: [servedRun] }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    await useDataStore.getState().serveCheckpoint(EP, "run-1");
    expect(useDataStore.getState().runs[0].served).toBe(true);
    const calls = fetchMock.mock.calls.map((c) => c[0] as string);
    expect(calls.some((u) => u.includes("/serve"))).toBe(true);
  });
});
