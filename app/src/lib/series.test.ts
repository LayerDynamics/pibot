import { describe, expect, it } from "vitest";

import { LatencySeries, MAX_SAMPLES, STALE_THRESHOLD_MS } from "./series";

function makeSample(inferMs: number, chunkAgeMs: number, ts = 0): Parameters<LatencySeries["push"]>[0] {
  return { ts, inferMs, stale: chunkAgeMs > STALE_THRESHOLD_MS };
}

describe("LatencySeries", () => {
  it("starts empty", () => {
    const s = new LatencySeries();
    expect(s.length).toBe(0);
    expect(s.samples).toHaveLength(0);
    expect(s.isCurrentlyStale()).toBe(false);
  });

  it("accumulates samples", () => {
    const s = new LatencySeries();
    s.push(makeSample(10.0, 100));
    s.push(makeSample(12.0, 200));
    expect(s.length).toBe(2);
    expect(s.samples[0].inferMs).toBeCloseTo(10.0);
    expect(s.samples[1].inferMs).toBeCloseTo(12.0);
  });

  it("drops oldest when window is full", () => {
    const s = new LatencySeries();
    for (let i = 0; i < MAX_SAMPLES + 10; i++) {
      s.push(makeSample(i, 0, i));
    }
    expect(s.length).toBe(MAX_SAMPLES);
    // The oldest entries are gone; the latest is the last pushed.
    expect(s.samples[s.length - 1].ts).toBe(MAX_SAMPLES + 9);
  });

  it("isCurrentlyStale is true when latest sample has stale flag", () => {
    const s = new LatencySeries();
    s.push(makeSample(10.0, 100));      // fresh
    expect(s.isCurrentlyStale()).toBe(false);
    s.push(makeSample(10.0, 1500));     // stale (1500 > 1000)
    expect(s.isCurrentlyStale()).toBe(true);
  });

  it("isCurrentlyStale clears when a fresh sample arrives", () => {
    const s = new LatencySeries();
    s.push(makeSample(10.0, 2000));     // stale
    expect(s.isCurrentlyStale()).toBe(true);
    s.push(makeSample(10.0, 500));      // fresh
    expect(s.isCurrentlyStale()).toBe(false);
  });

  it("stale flag is set at STALE_THRESHOLD_MS boundary", () => {
    const s = new LatencySeries();
    s.push(makeSample(10.0, STALE_THRESHOLD_MS));      // exactly at threshold → not stale
    expect(s.isCurrentlyStale()).toBe(false);
    s.push(makeSample(10.0, STALE_THRESHOLD_MS + 1));  // over threshold → stale
    expect(s.isCurrentlyStale()).toBe(true);
  });

  it("clear empties the series", () => {
    const s = new LatencySeries();
    s.push(makeSample(10.0, 100));
    s.clear();
    expect(s.length).toBe(0);
    expect(s.isCurrentlyStale()).toBe(false);
  });
});
