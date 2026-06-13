import { describe, expect, it } from "vitest";

import { MAX_V, MAX_W, teleopMap } from "./teleopMap";

describe("teleopMap", () => {
  it("W maps to positive v", () => {
    const out = teleopMap(new Set(["KeyW"]));
    expect(out.v).toBeCloseTo(MAX_V);
    expect(out.w).toBe(0);
  });

  it("S maps to negative v", () => {
    const out = teleopMap(new Set(["KeyS"]));
    expect(out.v).toBeCloseTo(-MAX_V);
    expect(out.w).toBe(0);
  });

  it("A maps to positive w (turn left)", () => {
    const out = teleopMap(new Set(["KeyA"]));
    expect(out.v).toBe(0);
    expect(out.w).toBeCloseTo(MAX_W);
  });

  it("D maps to negative w (turn right)", () => {
    const out = teleopMap(new Set(["KeyD"]));
    expect(out.v).toBe(0);
    expect(out.w).toBeCloseTo(-MAX_W);
  });

  it("ArrowLeft maps to positive w", () => {
    const out = teleopMap(new Set(["ArrowLeft"]));
    expect(out.w).toBeCloseTo(MAX_W);
  });

  it("ArrowRight maps to negative w", () => {
    const out = teleopMap(new Set(["ArrowRight"]));
    expect(out.w).toBeCloseTo(-MAX_W);
  });

  it("ArrowUp maps to positive v", () => {
    const out = teleopMap(new Set(["ArrowUp"]));
    expect(out.v).toBeCloseTo(MAX_V);
  });

  it("ArrowDown maps to negative v", () => {
    const out = teleopMap(new Set(["ArrowDown"]));
    expect(out.v).toBeCloseTo(-MAX_V);
  });

  it("no keys pressed → stop", () => {
    const out = teleopMap(new Set());
    expect(out.v).toBe(0);
    expect(out.w).toBe(0);
  });

  it("W+A combines forward+left", () => {
    const out = teleopMap(new Set(["KeyW", "KeyA"]));
    expect(out.v).toBeCloseTo(MAX_V);
    expect(out.w).toBeCloseTo(MAX_W);
  });

  it("W+S cancel each other out", () => {
    const out = teleopMap(new Set(["KeyW", "KeyS"]));
    expect(out.v).toBe(0);
  });

  it("Escape → stop regardless of other keys", () => {
    const out = teleopMap(new Set(["KeyW", "Escape"]));
    expect(out.v).toBe(0);
    expect(out.w).toBe(0);
  });

  it("v is clamped to [-MAX_V, MAX_V]", () => {
    const out = teleopMap(new Set(["KeyW"]));
    expect(Math.abs(out.v)).toBeLessThanOrEqual(MAX_V);
  });

  it("w is clamped to [-MAX_W, MAX_W]", () => {
    const out = teleopMap(new Set(["KeyA"]));
    expect(Math.abs(out.w)).toBeLessThanOrEqual(MAX_W);
  });
});
