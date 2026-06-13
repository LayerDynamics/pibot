import { describe, expect, it } from "vitest";

import { MAX_V, MAX_W } from "./teleopMap";
import { DEADZONE, gamepadMap } from "./gamepadMap";

function axes(leftY = 0, rightX = 0): number[] {
  // Standard gamepad layout: axes[1]=left-stick Y, axes[2]=right-stick X
  return [0, leftY, rightX, 0];
}

function btns(count = 17, faceIdx = 0, pressed = false): GamepadButton[] {
  return Array.from({ length: count }, (_, i) => ({
    pressed: i === faceIdx ? pressed : false,
    touched: false,
    value: i === faceIdx && pressed ? 1 : 0,
  }));
}

describe("gamepadMap", () => {
  it("neutral sticks → zero v and w", () => {
    const out = gamepadMap(axes(0, 0), btns());
    expect(out.v).toBe(0);
    expect(out.w).toBe(0);
  });

  it("left-stick Y fully forward → +MAX_V", () => {
    const out = gamepadMap(axes(-1, 0), btns()); // -1 = forward (gamepad convention)
    expect(out.v).toBeCloseTo(MAX_V);
  });

  it("left-stick Y fully back → -MAX_V", () => {
    const out = gamepadMap(axes(1, 0), btns());
    expect(out.v).toBeCloseTo(-MAX_V);
  });

  it("right-stick X fully left → +MAX_W", () => {
    const out = gamepadMap(axes(0, -1), btns());
    expect(out.w).toBeCloseTo(MAX_W);
  });

  it("right-stick X fully right → -MAX_W", () => {
    const out = gamepadMap(axes(0, 1), btns());
    expect(out.w).toBeCloseTo(-MAX_W);
  });

  it("values within deadzone → zero", () => {
    const out = gamepadMap(axes(DEADZONE * 0.9, DEADZONE * 0.9), btns());
    expect(out.v).toBe(0);
    expect(out.w).toBe(0);
  });

  it("face button A (index 0) pressed → stop", () => {
    const out = gamepadMap(axes(-1, 0), btns(17, 0, true));
    expect(out.v).toBe(0);
    expect(out.w).toBe(0);
  });

  it("partial stick deflection scales linearly beyond deadzone", () => {
    const half = (1 + DEADZONE) / 2; // midpoint between deadzone edge and 1
    const out = gamepadMap(axes(-half, 0), btns());
    expect(out.v).toBeGreaterThan(0);
    expect(out.v).toBeLessThan(MAX_V);
  });

  it("v and w are clamped to their limits", () => {
    const out = gamepadMap(axes(-2, 2), btns());
    expect(out.v).toBeCloseTo(MAX_V);
    expect(out.w).toBeCloseTo(-MAX_W);
  });
});
