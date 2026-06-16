import { create } from "zustand";

import type {
  ArmPose,
  ArmProgram,
  ArmProgramStatus,
  ArmReply,
  ArmTelemetry,
  McEndpoint,
} from "../lib/api/types";

// A sample older than this (server-computed age) means the arm drain loop has stalled.
const STALE_THRESHOLD_MS = 1000;

interface ArmState {
  enabled: boolean;
  numJoints: number;
  positions: Record<string, number>;
  homed: Record<string, boolean>;
  estopped: boolean;
  gripper: { deg: number; tool: boolean } | null;
  pose: { x: number; y: number; z: number; rx: number; ry: number; rz: number } | null;
  programStatus: ArmProgramStatus | null;
  ageMs: number | null;
  stale: boolean;
  poses: ArmPose[];
  programs: ArmProgram[];
  /** True once a fetch has succeeded, so the screen can distinguish "no data yet" from "no arm". */
  loaded: boolean;
  error: string | null;
  fetch: (ep: McEndpoint) => Promise<void>;
  fetchPoses: (ep: McEndpoint) => Promise<void>;
  poseSave: (ep: McEndpoint, name: string) => Promise<void>;
  fetchPrograms: (ep: McEndpoint) => Promise<void>;
  saveProgram: (ep: McEndpoint, program: ArmProgram) => Promise<void>;
  runProgram: (ep: McEndpoint, name: string) => Promise<void>;
  stopProgram: (ep: McEndpoint) => Promise<void>;
  jog: (ep: McEndpoint, joint: number, dps: number) => Promise<void>;
  moveJoint: (ep: McEndpoint, joint: number, deg: number, speed?: number) => Promise<void>;
  home: (ep: McEndpoint, joint: number) => Promise<void>;
  estop: (ep: McEndpoint) => Promise<void>;
  clearEstop: (ep: McEndpoint) => Promise<void>;
  enable: (ep: McEndpoint, on: boolean) => Promise<void>;
  grip: (ep: McEndpoint, deg: number) => Promise<void>;
  tool: (ep: McEndpoint, on: boolean) => Promise<void>;
  moveCartesian: (
    ep: McEndpoint,
    x: number,
    y: number,
    z: number,
    seconds: number,
    orientation?: { rx?: number; ry?: number; rz?: number },
  ) => Promise<void>;
  reset: () => void;
}

async function authed(ep: McEndpoint, path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${ep.url}${path}`, {
    ...init,
    headers: { ...(init.headers ?? {}), Authorization: `Bearer ${ep.token}` },
  });
}

type Setter = (partial: Partial<ArmState>) => void;

async function requestJson<T>(
  set: Setter,
  ep: McEndpoint,
  path: string,
  init: RequestInit = {},
): Promise<T | null> {
  try {
    const r = await authed(ep, path, init);
    if (!r.ok) {
      const text = await r.text();
      set({ error: `${path} failed (${r.status}): ${text}` });
      return null;
    }
    const data = (await r.json()) as T;
    set({ error: null });
    return data;
  } catch (e) {
    set({ error: String(e) });
    return null;
  }
}

/** POST a motion intent to the MC proxy; surface a transport error or a host-gate nak. Returns
 * whether the command was accepted (HTTP ok AND not a nak), so callers can update optimistic
 * state (e.g. the e-stop latch) only on success. */
async function motion(
  set: Setter,
  ep: McEndpoint,
  path: string,
  body?: Record<string, unknown>,
): Promise<boolean> {
  try {
    const r = await authed(ep, path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    });
    if (!r.ok) {
      const text = await r.text();
      set({ error: `${path} failed (${r.status}): ${text}` });
      return false;
    }
    const reply = (await r.json()) as ArmReply;
    if (reply.type === "nak") {
      set({ error: `refused: ${reply.reason ?? "unknown"}` });
      return false;
    }
    set({ error: null });
    return true;
  } catch (e) {
    set({ error: String(e) });
    return false;
  }
}

const EMPTY: Pick<
  ArmState,
  | "enabled"
  | "numJoints"
  | "positions"
  | "homed"
  | "estopped"
  | "gripper"
  | "pose"
  | "programStatus"
  | "ageMs"
  | "stale"
  | "poses"
  | "programs"
  | "loaded"
  | "error"
> = {
  enabled: false,
  numJoints: 0,
  positions: {},
  homed: {},
  estopped: false,
  gripper: null,
  pose: null,
  programStatus: null,
  ageMs: null,
  stale: false,
  poses: [],
  programs: [],
  loaded: false,
  error: null,
};

export const useArmStore = create<ArmState>((set) => ({
  ...EMPTY,

  fetch: async (ep) => {
    try {
      const r = await authed(ep, "/api/arm/telemetry");
      if (!r.ok) {
        const text = await r.text();
        set({ error: `arm telemetry failed (${r.status}): ${text}` });
        return;
      }
      const data: ArmTelemetry = await r.json();
      const stale = data.age_ms !== null && data.age_ms > STALE_THRESHOLD_MS;
      set({
        enabled: data.enabled,
        numJoints: data.num_joints,
        positions: data.positions ?? {},
        homed: data.homed ?? {},
        estopped: data.estopped ?? false,
        gripper: data.gripper ?? null,
        pose: data.pose ?? null,
        programStatus: data.program ?? null,
        ageMs: data.age_ms,
        stale,
        loaded: true,
        error: null,
      });
    } catch (e) {
      set({ error: String(e) });
    }
  },

  fetchPoses: async (ep) => {
    const data = await requestJson<{ poses: ArmPose[] }>(set, ep, "/api/arm/poses");
    if (data) set({ poses: data.poses ?? [] });
  },

  poseSave: async (ep, name) => {
    const data = await requestJson<ArmPose>(set, ep, "/api/arm/poses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (data) {
      set((state) => ({
        poses: [...state.poses.filter((pose) => pose.name !== data.name), data].sort((a, b) =>
          a.name.localeCompare(b.name),
        ),
      }));
    }
  },

  fetchPrograms: async (ep) => {
    const data = await requestJson<{ programs: ArmProgram[] }>(set, ep, "/api/arm/programs");
    if (data) set({ programs: data.programs ?? [] });
  },

  saveProgram: async (ep, program) => {
    const data = await requestJson<ArmProgram>(set, ep, "/api/arm/programs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(program),
    });
    if (data) {
      set((state) => ({
        programs: [
          ...state.programs.filter((existing) => existing.name !== data.name),
          data,
        ].sort((a, b) => a.name.localeCompare(b.name)),
      }));
    }
  },

  runProgram: async (ep, name) => {
    await requestJson(set, ep, `/api/arm/programs/${encodeURIComponent(name)}/run`, {
      method: "POST",
    });
  },

  stopProgram: async (ep) => {
    await requestJson(set, ep, "/api/arm/programs/stop", { method: "POST" });
  },

  jog: async (ep, joint, dps) => {
    await motion(set, ep, "/api/arm/jog", { joint, dps });
  },

  moveJoint: async (ep, joint, deg, speed) => {
    const body = speed === undefined ? { joint, deg } : { joint, deg, speed };
    await motion(set, ep, "/api/arm/move", body);
  },

  home: async (ep, joint) => {
    await motion(set, ep, "/api/arm/home", { joint });
  },

  estop: async (ep) => {
    // Latch optimistically so jog locks out immediately; the next fetch confirms from pibotd.
    if (await motion(set, ep, "/api/arm/estop")) set({ estopped: true });
  },

  clearEstop: async (ep) => {
    if (await motion(set, ep, "/api/arm/clear_estop")) set({ estopped: false });
  },

  enable: async (ep, on) => {
    await motion(set, ep, "/api/arm/enable", { on });
  },

  grip: async (ep, deg) => {
    await motion(set, ep, "/api/arm/grip", { deg });
  },

  tool: async (ep, on) => {
    await motion(set, ep, "/api/arm/tool", { on });
  },

  moveCartesian: async (ep, x, y, z, seconds, orientation) => {
    await motion(set, ep, "/api/arm/move-cartesian", {
      x,
      y,
      z,
      seconds,
      rx: orientation?.rx ?? 0,
      ry: orientation?.ry ?? 0,
      rz: orientation?.rz ?? 0,
    });
  },

  reset: () => set({ ...EMPTY }),
}));
