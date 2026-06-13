import { create } from "zustand";

import type { McEndpoint } from "../lib/api/types";

export type OpsStatus =
  | "queued"
  | "preview"
  | "awaiting-confirm"
  | "running"
  | "done"
  | "error"
  | "cancelled";

export interface OpsJob {
  id: string;
  kind: string;
  args: Record<string, string>;
  dry_run: boolean;
  confirmed: boolean;
  guard_passed: boolean;
  status: OpsStatus;
  progress: number;
  log: string[];
}

interface OpsState {
  job: OpsJob | null;
  confirmPending: boolean;
  guardAcknowledged: boolean;
  error: string | null;

  submit: (ep: McEndpoint, kind: string, args: Record<string, string>) => Promise<void>;
  acknowledgeGuard: () => void;
  confirm: (ep: McEndpoint) => Promise<void>;
  cancel: (ep: McEndpoint) => Promise<void>;
  reset: () => void;
}

function auth(ep: McEndpoint) {
  return { Authorization: `Bearer ${ep.token}`, "Content-Type": "application/json" };
}

export const useOpsStore = create<OpsState>((set, get) => ({
  job: null,
  confirmPending: false,
  guardAcknowledged: false,
  error: null,

  async submit(ep, kind, args) {
    set({ job: null, confirmPending: false, guardAcknowledged: false, error: null });
    const r = await fetch(`${ep.url}/api/ops/${kind}`, {
      method: "POST",
      headers: auth(ep),
      body: JSON.stringify(args),
    });
    if (!r.ok) {
      set({ error: `submit failed: ${r.status}` });
      return;
    }
    const job: OpsJob = await r.json();
    set({ job, confirmPending: job.status === "awaiting-confirm" });
  },

  acknowledgeGuard() {
    set({ guardAcknowledged: true });
  },

  async confirm(ep) {
    const { job, guardAcknowledged } = get();
    if (!job) return;
    // The confirm button must not fire unless guardAcknowledged (destructive guard)
    if (!guardAcknowledged) return;
    const r = await fetch(`${ep.url}/api/ops/${job.id}/confirm`, {
      method: "POST",
      headers: auth(ep),
      body: JSON.stringify({ guard_passed: guardAcknowledged }),
    });
    if (!r.ok) {
      const text = await r.text();
      set({ error: text });
      return;
    }
    const updated: OpsJob = await r.json();
    set({ job: updated, confirmPending: false });
  },

  async cancel(ep) {
    const { job } = get();
    if (!job) return;
    const r = await fetch(`${ep.url}/api/ops/${job.id}/cancel`, {
      method: "POST",
      headers: auth(ep),
    });
    if (r.ok) {
      const updated: OpsJob = await r.json();
      set({ job: updated });
    }
  },

  reset() {
    set({ job: null, confirmPending: false, guardAcknowledged: false, error: null });
  },
}));
