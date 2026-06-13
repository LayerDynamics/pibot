/**
 * Task prompts — kept in lockstep with pibot/config.py TASK_PROMPTS.
 * These are the canonical prompt strings used for demonstration recording and autonomy.
 */

export const TASK_PROMPTS: Record<string, string> = {
  goal: "drive to the red ball",
  follow: "follow me",
  explore: "explore the room",
};

export const TASK_KEYS = Object.keys(TASK_PROMPTS) as Array<keyof typeof TASK_PROMPTS>;
