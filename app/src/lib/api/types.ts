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
