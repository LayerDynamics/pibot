/**
 * Local control-plane contract (SPEC-3 §3.4 / Appendix B). Mirror of the Python
 * `pibot/mc/types.py` + the pibotd telemetry snapshot shape — keep them in lockstep.
 */

export interface McEndpoint {
  url: string;
  token: string;
}

export interface Throttled {
  raw?: number;
  currently: string[];
}

export interface PiHealth {
  temp_c?: number | null;
  core_volt?: number | null;
  cpu_pct?: number | null;
  mem_pct?: number | null;
  throttled?: Throttled;
  disk?: { pct?: number | null };
}

export interface PolicyLink {
  connected: boolean | null;
  last_inference_ms: number | null;
  chunk_age_ms: number | null;
}

export interface Snapshot {
  ts: number;
  pi: PiHealth;
  robot: { battery?: { volts?: number | null } } & Record<string, unknown>;
  transport: { open?: boolean | null; backend?: string | null; kind?: string | null };
  safety: { estop: boolean };
  policy: PolicyLink;
}

export interface Health {
  ok: boolean;
  version: string;
  connected: boolean;
  robot: string | null;
}

export interface RobotEntry {
  alias: string;
  address: string;
  ip: string;
  hostname: string;
  user: string | null;
  link: string;
  pi: boolean;
}

export interface Episode {
  id: string;
  task: string;
  length: number;
  started: number;
  ended: number;
}

export interface FineTuneRun {
  id: string;
  dataset: string;
  status: string;
  checkpoint_out: string | null;
  served: boolean;
}

export interface TelemetryRow {
  ts: number;
  temp_c: number | null;
  battery_v: number | null;
  estop: number;
  transport_open: number;
  policy_connected: number;
  last_infer_ms: number | null;
  chunk_age_ms: number | null;
}

export interface HistoryQuery {
  from: number;
  to: number;
  fields?: string[];
}

/** Stepper-arm state (mirror of pibotd `GET /arm/telemetry`). `positions` and `homed` are keyed
 * by logical joint id (as a string, per JSON); `ts` is the agent's last sample time. `homed` and
 * `estopped` come from the host gate state, so the UI reflects real homing + latch state. */
export interface ArmTelemetry {
  ok: boolean;
  enabled: boolean;
  num_joints: number;
  positions: Record<string, number>;
  /** Per-joint homing flag (host-tracked; absolute moves are refused until a joint is homed). */
  homed: Record<string, boolean>;
  /** Whether the arm e-stop is latched (all motion refused until cleared). */
  estopped: boolean;
  /** End-effector state (servo angle + tool digital-out), or null when none is configured/reported. */
  gripper: { deg: number; tool: boolean } | null;
  /** Forward-kinematics end-effector pose (position m, orientation rad), or null without the
   * `[arm-ik]` extra / no joint angles yet. */
  pose: { x: number; y: number; z: number; rx: number; ry: number; rz: number } | null;
  ts: number;
  /** Server-computed age of the cached sample in ms (null until the first sample). */
  age_ms: number | null;
}

/** pibotd's per-frame reply to an `/api/arm/*` motion call. */
export interface ArmReply {
  type: "ack" | "nak";
  reason?: string;
}
