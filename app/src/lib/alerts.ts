/**
 * Threshold alerts — a faithful TypeScript port of `pibot/monitor.check_thresholds`.
 * Keep the cases and thresholds in lockstep with that function (SPEC-3 FR-5).
 */

import type { Snapshot } from "./api/types";

export interface AlertThresholds {
  tempWarn: number;
  batteryWarn: number;
  policyStaleMs: number;
}

export const DEFAULT_THRESHOLDS: AlertThresholds = {
  tempWarn: 80,
  batteryWarn: 11,
  policyStaleMs: 1000,
};

export function alerts(snap: Snapshot, t: AlertThresholds = DEFAULT_THRESHOLDS): string[] {
  const out: string[] = [];

  const temp = snap.pi?.temp_c;
  if (temp != null && temp >= t.tempWarn) {
    out.push(`temp ${temp}°C ≥ ${t.tempWarn}°C`);
  }

  const currently = snap.pi?.throttled?.currently ?? [];
  if (currently.length > 0) {
    out.push(`throttled: ${currently.join(", ")}`);
  }

  const battery = snap.robot?.battery?.volts;
  if (battery != null && battery < t.batteryWarn) {
    out.push(`battery ${battery}V < ${t.batteryWarn}V`);
  }

  if (snap.transport?.open === false) {
    out.push("transport down");
  }

  if (snap.safety?.estop) {
    out.push("e-stop latched");
  }

  if (snap.policy?.connected === false) {
    out.push("policy down");
  }

  const age = snap.policy?.chunk_age_ms;
  if (age != null && age >= t.policyStaleMs) {
    out.push(`policy chunk stale ${age}ms ≥ ${t.policyStaleMs}ms`);
  }

  return out;
}
