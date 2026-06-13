import { describe, expect, it } from "vitest";

import { TASK_KEYS, TASK_PROMPTS } from "./tasks";

describe("TASK_PROMPTS", () => {
  it("has the three canonical task keys", () => {
    expect(TASK_KEYS).toContain("goal");
    expect(TASK_KEYS).toContain("follow");
    expect(TASK_KEYS).toContain("explore");
    expect(TASK_KEYS).toHaveLength(3);
  });

  it("goal maps to the canonical drive-to-ball prompt", () => {
    expect(TASK_PROMPTS["goal"]).toBe("drive to the red ball");
  });

  it("follow maps to the canonical follow prompt", () => {
    expect(TASK_PROMPTS["follow"]).toBe("follow me");
  });

  it("explore maps to the canonical explore prompt", () => {
    expect(TASK_PROMPTS["explore"]).toBe("explore the room");
  });

  it("every key has a non-empty prompt string", () => {
    for (const key of TASK_KEYS) {
      expect(typeof TASK_PROMPTS[key]).toBe("string");
      expect(TASK_PROMPTS[key].length).toBeGreaterThan(0);
    }
  });
});
