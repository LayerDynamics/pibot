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

/**
 * A press-and-hold jog button. Pointer-down jogs at `dir * JOG_DPS`; pointer-up, leave, AND
 * cancel all stop — so a touch/scroll/system-gesture interrupt (which fires neither up nor leave)
 * can't leave a joint jogging. Both ± buttons render through this one definition so the jog
 * interaction is defined in a single place and the two directions can't diverge.
 */
function JogButton({
  jid,
  dir,
  label,
  disabled,
  onStart,
  onStop,
}: {
  jid: string;
  dir: 1 | -1;
  label: string;
  disabled: boolean;
  onStart: (jid: string, dir: number) => void;
  onStop: (jid: string) => void;
}) {
  return (
    <button
      type="button"
      data-testid={`arm-jog-${dir < 0 ? "neg" : "pos"}-${jid}`}
      disabled={disabled}
      onPointerDown={() => onStart(jid, dir)}
      onPointerUp={() => onStop(jid)}
      onPointerLeave={() => onStop(jid)}
      onPointerCancel={() => onStop(jid)}
      className="rounded bg-zinc-700 px-3 py-1 text-sm text-zinc-100 hover:bg-zinc-600 disabled:opacity-40"
    >
      {label}
    </button>
  );
}

export default function Arm({ ep }: Props) {
  const connected = useConnectionStore((s) => s.state === "connected");
  const {
    enabled,
    numJoints,
    positions,
    homed,
    estopped,
    gripper,
    pose,
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
    grip,
    tool,
    moveCartesian,
    reset,
  } = useArmStore();

  const [goal, setGoal] = useState<Record<string, string>>({});
  const [gripGoal, setGripGoal] = useState(0);
  const [xyzGoal, setXyzGoal] = useState({ x: "0", y: "0", z: "0", seconds: "2" });

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

  const goCartesian = () => {
    const x = Number.parseFloat(xyzGoal.x);
    const y = Number.parseFloat(xyzGoal.y);
    const z = Number.parseFloat(xyzGoal.z);
    const seconds = Number.parseFloat(xyzGoal.seconds);
    if (ep && ![x, y, z, seconds].some(Number.isNaN)) {
      // mm -> m at the UI boundary; orientation defaults to level (rx=ry=rz=0).
      void moveCartesian(ep, x / 1000, y / 1000, z / 1000, seconds);
    }
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

          {/* End-effector Cartesian pose from forward kinematics (M-ARM-3); shown only when the
              robot has the [arm-ik] extra (else `pose` is null). */}
          {pose && (
            <div
              data-testid="arm-ee-pose"
              className="rounded border border-zinc-800 px-3 py-2 font-mono text-xs text-zinc-300"
            >
              EE&nbsp; x {(pose.x * 1000).toFixed(0)} &nbsp; y {(pose.y * 1000).toFixed(0)} &nbsp; z{" "}
              {(pose.z * 1000).toFixed(0)} mm
            </div>
          )}

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
                    <JogButton
                      jid={jid}
                      dir={-1}
                      label="−"
                      disabled={jogDisabled}
                      onStart={startJog}
                      onStop={stopJog}
                    />
                    <JogButton
                      jid={jid}
                      dir={1}
                      label="+"
                      disabled={jogDisabled}
                      onStart={startJog}
                      onStop={stopJog}
                    />
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

          {/* End-effector — servo gripper + optional digital-output tool (M-ARM-2). Refused while
              e-stop is latched, like joint motion. */}
          <div
            className="flex flex-col gap-2 rounded border border-zinc-800 px-3 py-2"
            data-testid="arm-gripper"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-zinc-300">Gripper</span>
              <span data-testid="arm-gripper-readout" className="font-mono text-xs text-zinc-200">
                {gripper
                  ? `${gripper.deg.toFixed(0)}° · tool ${gripper.tool ? "on" : "off"}`
                  : "—"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="range"
                min={0}
                max={180}
                step={1}
                data-testid="arm-grip-slider"
                value={gripGoal}
                disabled={!canControl || estopped}
                onChange={(e) => setGripGoal(Number(e.target.value))}
                className="flex-1"
              />
              <span className="w-10 text-right font-mono text-xs text-zinc-300">{gripGoal}°</span>
              <button
                type="button"
                data-testid="arm-grip-set"
                disabled={!canControl || estopped}
                onClick={() => ep && void grip(ep, gripGoal)}
                className="rounded bg-sky-700 px-3 py-1 text-sm text-zinc-100 hover:bg-sky-600 disabled:opacity-40"
              >
                Set
              </button>
              <button
                type="button"
                data-testid="arm-grip-open"
                disabled={!canControl || estopped}
                onClick={() => ep && void grip(ep, 0)}
                className="rounded bg-zinc-700 px-3 py-1 text-sm text-zinc-100 hover:bg-zinc-600 disabled:opacity-40"
              >
                Open
              </button>
              <button
                type="button"
                data-testid="arm-grip-close"
                disabled={!canControl || estopped}
                onClick={() => ep && void grip(ep, 180)}
                className="rounded bg-zinc-700 px-3 py-1 text-sm text-zinc-100 hover:bg-zinc-600 disabled:opacity-40"
              >
                Close
              </button>
              <button
                type="button"
                data-testid="arm-tool-toggle"
                disabled={!canControl || estopped}
                onClick={() => ep && void tool(ep, !(gripper?.tool ?? false))}
                className="rounded bg-zinc-700 px-3 py-1 text-sm text-zinc-100 hover:bg-zinc-600 disabled:opacity-40"
              >
                Tool {gripper?.tool ? "off" : "on"}
              </button>
            </div>
          </div>

          {/* Cartesian end-effector move via on-Pi IK (M-ARM-4). Only shown when the agent has
              reported an FK pose — the same [arm-ik] extra + model gate IK, so a pose-less arm
              degrades gracefully to joint-only control instead of offering a move that will nak. */}
          {pose && (
            <div
              className="flex flex-col gap-2 rounded border border-zinc-800 px-3 py-2"
              data-testid="arm-cartesian"
            >
              <span className="text-xs font-medium text-zinc-300">Move to (mm)</span>
              <div className="flex items-center gap-2">
                {(["x", "y", "z"] as const).map((axis) => (
                  <input
                    key={axis}
                    type="number"
                    data-testid={`arm-xyz-${axis}`}
                    value={xyzGoal[axis]}
                    disabled={!canControl || estopped}
                    onChange={(e) => setXyzGoal({ ...xyzGoal, [axis]: e.target.value })}
                    className="w-20 rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
                    placeholder={axis}
                  />
                ))}
                <input
                  type="number"
                  data-testid="arm-xyz-seconds"
                  value={xyzGoal.seconds}
                  disabled={!canControl || estopped}
                  onChange={(e) => setXyzGoal({ ...xyzGoal, seconds: e.target.value })}
                  className="w-16 rounded bg-zinc-800 px-2 py-1 text-sm text-zinc-100"
                  placeholder="s"
                />
                <button
                  type="button"
                  data-testid="arm-xyz-go"
                  disabled={!canControl || estopped}
                  onClick={goCartesian}
                  className="rounded bg-sky-700 px-3 py-1 text-sm text-zinc-100 hover:bg-sky-600 disabled:opacity-40"
                >
                  Go
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
