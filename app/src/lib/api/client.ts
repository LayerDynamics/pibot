/**
 * Runtime client for the loopback control-plane API. The endpoint + per-launch token
 * come from the Rust core via the `mc_endpoint` command; HTTP calls send the bearer
 * header, and the telemetry WebSocket passes the token via `?token=` (browsers can't set
 * WS headers — the sidecar middleware accepts both, SPEC-3 §3.7).
 */

import { invoke } from "@tauri-apps/api/core";

import type { Health, McEndpoint, RobotEntry, Snapshot } from "./types";

export async function mcEndpoint(): Promise<McEndpoint> {
  return invoke<McEndpoint>("mc_endpoint");
}

async function authed(ep: McEndpoint, path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${ep.url}${path}`, {
    ...init,
    headers: { ...(init.headers ?? {}), Authorization: `Bearer ${ep.token}` },
  });
}

export async function getHealth(ep: McEndpoint): Promise<Health> {
  return (await authed(ep, "/api/health")).json() as Promise<Health>;
}

export async function listRobots(ep: McEndpoint): Promise<RobotEntry[]> {
  return (await authed(ep, "/api/robots")).json() as Promise<RobotEntry[]>;
}

export async function connectRobot(ep: McEndpoint, robot: string): Promise<void> {
  const r = await authed(ep, "/api/connect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ robot }),
  });
  if (!r.ok) {
    throw new Error(`connect failed (${r.status})`);
  }
}

export async function disconnectRobot(ep: McEndpoint): Promise<void> {
  await authed(ep, "/api/disconnect", { method: "POST" });
}

export function openTelemetry(ep: McEndpoint, onSnapshot: (s: Snapshot) => void): WebSocket {
  const wsUrl =
    ep.url.replace(/^http/, "ws") + `/api/telemetry?token=${encodeURIComponent(ep.token)}`;
  const ws = new WebSocket(wsUrl);
  ws.onmessage = (event) => {
    const data = typeof event.data === "string" ? event.data : "";
    if (!data) {
      return;
    }
    let snap: Snapshot | null = null;
    try {
      snap = JSON.parse(data) as Snapshot;
    } catch {
      snap = null;
    }
    if (snap) {
      onSnapshot(snap);
    }
  };
  return ws;
}
