/**
 * Arm screen — live joint telemetry **and** motion control for the stepper arm. pibotd owns the
 * ArmManager, the serial link, and the host safety gate; this screen drives the sidecar's
 * `/api/arm/*` proxy while connected. Absolute moves are gated on homing; an always-visible
 * E-Stop latches all motion until cleared (jog locks out while latched).
 */
import { useEffect, useState } from "react";

import type { McEndpoint } from "../lib/api/types";
import { useArmStore } from "../stores/armStore";
import { useConnectionStore } from "../stores/connectionStore";

interface Props {
  ep: McEndpoint | null;
}

const POLL_MS = 250;
// Joint angles span roughly [-180, 180]°; map that to a 0–100% bar fill.
const ANGLE_SPAN_DEG = 180;
// Fixed velocity for the ± jog buttons (deg/sec); held down to move, released to stop.
const JOG_DPS = 15;

function barFill(deg: number): number {
  const clamped = Math.max(-ANGLE_SPAN_DEG, Math.min(ANGLE_SPAN_DEG, deg));
  return ((clamped + ANGLE_SPAN_DEG) / (2 * ANGLE_SPAN_DEG)) * 100;
}

export default function Arm({ ep }: Props) {
  const connected = useConnectionStore((s) => s.state === "connected");
  const {
    enabled,
    numJoints,
    positions,
    homed,
    estopped,
    ageMs,
    stale,
    loaded,
    error,
    fetch,
    jog,
    moveJoint,
    home,
    estop,
    clearEstop,
    enable,
    reset,
  } = useArmStore();

  const [goal, setGoal] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!ep || !connected) {
      reset();
      return;
    }
    void fetch(ep);
    const id = setInterval(() => void fetch(ep), POLL_MS);
    return () => {
      clearInterval(id);
      reset();
    };
  }, [ep, connected, fetch, reset]);

  const jointIds = Array.from({ length: numJoints }, (_, i) => String(i));
  const canControl = connected && enabled && ep !== null;
  const jogDisabled = !canControl || estopped;

  const startJog = (jid: string, dir: number) => {
    if (ep && !jogDisabled) void jog(ep, Number(jid), dir * JOG_DPS);
  };
  const stopJog = (jid: string) => {
    if (ep && canControl) void jog(ep, Number(jid), 0);
  };
  const goTo = (jid: string) => {
    const deg = Number.parseFloat(goal[jid] ?? "");
    if (ep && !Number.isNaN(deg)) void moveJoint(ep, Number(jid), deg);
  };

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="arm-screen">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-200">Arm</h2>
        {enabled && (
          <span
            data-testid="arm-freshness"
            className={`rounded-full px-2 py-0.5 text-xs ${
              stale ? "bg-amber-900 text-amber-300" : "bg-emerald-900 text-emerald-300"
            }`}
          >
            {stale ? "stale" : "live"}
            {ageMs !== null && ` · ${Math.round(ageMs)} ms`}
          </span>
        )}
      </div>

      {!connected && <p className="text-xs text-zinc-500">Connect to a robot to view the arm.</p>}
      {connected && error && (
        <p className="text-xs text-red-400" data-testid="arm-error">
          {error}
        </p>
      )}
      {connected && loaded && !enabled && (
        <p className="text-xs text-zinc-500">No arm configured on this robot.</p>
      )}

      {connected && enabled && (
        <>
          {/* Whole-arm controls — E-Stop is always reachable; it latches until cleared. */}
          <div className="flex flex-wrap items-center gap-2" data-testid="arm-controls">
            <button
              type="button"
              data-testid="arm-estop"
              onClick={() => ep && void estop(ep)}
              className="rounded bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-500"
            >
              E-Stop
            </button>
            <button
              type="button"
              data-testid="arm-clear"
              onClick={() => ep && void clearEstop(ep)}
              disabled={!estopped}
              className="rounded bg-zinc-700 px-3 py-1.5 text-sm text-zinc-100 hover:bg-zinc-600 disabled:opacity-40"
            >
              Clear
            </button>
            <button
              type="button"
              data-testid="arm-enable"
              onClick={() => ep && void enable(ep, true)}
              className="rounded bg-zinc-700 px-3 py-1.5 text-sm text-zinc-100 hover:bg-zinc-600"
            >
              Enable
            </button>
            <button
              type="button"
              data-testid="arm-disable"
              onClick={() => ep && void enable(ep, false)}
              className="rounded bg-zinc-700 px-3 py-1.5 text-sm text-zinc-100 hover:bg-zinc-600"
            >
              Disable
            </button>
            {estopped && (
              <span
                data-testid="arm-estop-latched"
                className="rounded-full bg-red-900 px-2 py-0.5 text-xs text-red-300"
              >
                e-stop latched
              </span>
            )}
          </div>

          <div className="flex flex-col gap-2" data-testid="arm-joints">
            {jointIds.map((jid) => {
              const deg = positions[jid];
              const present = typeof deg === "number";
              const isHomed = homed[jid] === true;
              return (
                <div
                  key={jid}
                  className="flex flex-col gap-2 rounded border border-zinc-800 px-3 py-2"
                  data-testid={`arm-joint-${jid}`}
                >
                  <div className="flex items-center gap-3">
                    <span className="w-8 text-xs font-medium text-zinc-300">J{jid}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded bg-zinc-800">
                      {present && (
                        <div className="h-full bg-sky-500" style={{ width: `${barFill(deg)}%` }} />
                      )}
                    </div>
                    <span className="w-20 text-right font-mono text-xs text-zinc-200">
                      {present ? `${deg.toFixed(1)}°` : "—"}
                    </span>
                    <span
                      data-testid={`arm-homed-${jid}`}
                      className={`w-20 text-right text-xs ${
                        isHomed ? "text-emerald-400" : "text-amber-400"
                      }`}
                    >
                      {isHomed ? "homed" : "not homed"}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      data-testid={`arm-jog-neg-${jid}`}
                      disabled={jogDisabled}
                      onPointerDown={() => startJog(jid, -1)}
                      onPointerUp={() => stopJog(jid)}
                      onPointerLeave={() => stopJog(jid)}
                      onPointerCancel={() => stopJog(jid)}
                      className="rounded bg-zinc-700 px-3 py-1 text-sm text-zinc-100 hover:bg-zinc-600 disabled:opacity-40"
                    >
                      −
                    </button>
                    <button
                      type="button"
                      data-testid={`arm-jog-pos-${jid}`}
                      disabled={jogDisabled}
                      onPointerDown={() => startJog(jid, 1)}
                      onPointerUp={() => stopJog(jid)}
                      onPointerLeave={() => stopJog(jid)}
                      onPointerCancel={() => stopJog(jid)}
                      className="rounded bg-zinc-700 px-3 py-1 text-sm text-zinc-100 hover:bg-zinc-600 disabled:opacity-40"
                    >
                      +
                    </button>
                    <button
                      type="button"
                      data-testid={`arm-home-${jid}`}
                      disabled={!canControl || estopped}
                      onClick={() => ep && void home(ep, Number(jid))}
                      className="rounded bg-zinc-700 px-3 py-1 text-sm text-zinc-100 hover:bg-zinc-600 disabled:opacity-40"
                    >
                      Home
                    </button>
                    <input
                      type="number"
                      inputMode="decimal"
                      placeholder="deg"
                      data-testid={`arm-goal-${jid}`}
                      value={goal[jid] ?? ""}
                      onChange={(e) => setGoal((g) => ({ ...g, [jid]: e.target.value }))}
                      className="w-20 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100"
                    />
                    <button
                      type="button"
                      data-testid={`arm-goto-${jid}`}
                      disabled={!canControl || estopped || !isHomed}
                      title={isHomed ? undefined : "home this joint before an absolute move"}
                      onClick={() => goTo(jid)}
                      className="rounded bg-sky-700 px-3 py-1 text-sm text-zinc-100 hover:bg-sky-600 disabled:opacity-40"
                    >
                      Go
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
