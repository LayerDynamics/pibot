import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import URDFLoader, { type URDFRobot } from "urdf-loader";

import {
  ARM_TWIN_COLORS,
  type ArmTwinModel,
  ARM_URDF_PATH,
  applyJointStatesToRobot,
  buildTwinJointStates,
  loadArmTwinModel,
} from "./armTwinModel";

interface ArmTwinProps {
  positions: Record<string, number>;
  pose: { x: number; y: number; z: number; rx: number; ry: number; rz: number } | null;
  loadModel?: (urdfPath?: string) => Promise<ArmTwinModel>;
  loadRobot?: (urdfPath: string) => Promise<URDFRobot>;
  onJointJog?: (joint: number, dragRatio: number) => void;
  onJointStop?: (joint: number) => void;
  onPoseMove?: (delta: { dxMm: number; dyMm: number }) => void;
}

async function loadArmTwinRobot(urdfPath: string): Promise<URDFRobot> {
  const loader = new URDFLoader();
  return loader.loadAsync(urdfPath);
}

export function ArmTwinScene({ children }: { children: ReactNode }) {
  return (
    <div
      data-testid="arm-twin-scene"
      className="h-80 overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950"
    >
      <Canvas camera={{ position: [0.45, 0.22, 0.36], fov: 42 }}>
        <color attach="background" args={["#09090b"]} />
        <ambientLight intensity={0.9} />
        <directionalLight position={[1.5, 2.5, 1.2]} intensity={1.6} />
        <directionalLight position={[-1.2, -1.5, 0.8]} intensity={0.5} />
        <gridHelper args={[0.8, 8, "#27272a", "#18181b"]} position={[0, -0.01, 0]} />
        {children}
        <OrbitControls enablePan={false} />
      </Canvas>
    </div>
  );
}

function formatPose(pose: ArmTwinProps["pose"]): string {
  if (!pose) return "EE pose unavailable";
  return `x ${(pose.x * 1000).toFixed(0)} · y ${(pose.y * 1000).toFixed(0)} · z ${(pose.z * 1000).toFixed(0)} mm`;
}

function pointerDelta(current: number, previous: number, fallback: number): number {
  if (Number.isFinite(current) && Number.isFinite(previous)) return current - previous;
  if (Number.isFinite(fallback)) return fallback;
  return 0;
}

export function ArmTwin({
  positions,
  pose,
  loadModel = loadArmTwinModel,
  loadRobot = loadArmTwinRobot,
  onJointJog,
  onJointStop,
  onPoseMove,
}: ArmTwinProps) {
  const [model, setModel] = useState<ArmTwinModel | null>(null);
  const [robot, setRobot] = useState<URDFRobot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const jointDragRef = useRef<{
    joint: number;
    totalDx: number;
    lastX: number;
  } | null>(null);
  const tcpDragRef = useRef<{
    startX: number;
    startY: number;
    lastX: number;
    lastY: number;
    totalDx: number;
    totalDy: number;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadTwin() {
      try {
        const nextModel = await loadModel(ARM_URDF_PATH);
        const nextRobot = await loadRobot(nextModel.urdfPath);
        if (cancelled) return;
        setModel(nextModel);
        setRobot(nextRobot);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      }
    }
    void loadTwin();
    return () => {
      cancelled = true;
    };
  }, [loadModel, loadRobot]);

  const states = useMemo(
    () => (model ? buildTwinJointStates(model, positions) : []),
    [model, positions],
  );

  useEffect(() => {
    if (!robot || !model) return;
    applyJointStatesToRobot(robot, states);
  }, [model, robot, states]);

  useEffect(() => {
    function handlePointerMove(event: PointerEvent) {
      const activeJoint = jointDragRef.current;
      if (activeJoint && onJointJog) {
        const nextTotalDx =
          activeJoint.totalDx + pointerDelta(event.clientX, activeJoint.lastX, event.movementX);
        jointDragRef.current = { ...activeJoint, totalDx: nextTotalDx, lastX: event.clientX };
        const ratio = Math.max(-1, Math.min(1, nextTotalDx / 80));
        onJointJog(activeJoint.joint, ratio);
      }

      const activeTcp = tcpDragRef.current;
      if (activeTcp) {
        tcpDragRef.current = {
          ...activeTcp,
          totalDx: activeTcp.totalDx + pointerDelta(event.clientX, activeTcp.lastX, event.movementX),
          totalDy: activeTcp.totalDy + pointerDelta(event.clientY, activeTcp.lastY, event.movementY),
          lastX: event.clientX,
          lastY: event.clientY,
        };
      }
    }

    function handlePointerUp(event: PointerEvent) {
      const activeJoint = jointDragRef.current;
      if (activeJoint) {
        onJointStop?.(activeJoint.joint);
        jointDragRef.current = null;
      }

      const activeTcp = tcpDragRef.current;
      if (activeTcp) {
        const dxMm =
          activeTcp.totalDx !== 0
            ? activeTcp.totalDx
            : pointerDelta(event.clientX, activeTcp.startX, 0);
        const dyMm =
          activeTcp.totalDy !== 0
            ? -activeTcp.totalDy
            : -pointerDelta(event.clientY, activeTcp.startY, 0);
        if ((dxMm !== 0 || dyMm !== 0) && onPoseMove) onPoseMove({ dxMm, dyMm });
        tcpDragRef.current = null;
      }
    }

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [onJointJog, onJointStop, onPoseMove]);

  if (error) {
    return (
      <div
        data-testid="arm-twin-fallback"
        className="rounded-xl border border-dashed border-zinc-800 bg-zinc-950/60 px-4 py-3 text-sm text-zinc-400"
      >
        Twin unavailable · {error}
      </div>
    );
  }

  if (!model || !robot) {
    return (
      <div
        data-testid="arm-twin-loading"
        className="rounded-xl border border-zinc-800 bg-zinc-950/60 px-4 py-3 text-sm text-zinc-400"
      >
        Loading twin…
      </div>
    );
  }

  return (
    <div
      data-testid="arm-twin-root"
      className="relative overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950/70"
    >
      <ArmTwinScene>
        <primitive object={robot} />
      </ArmTwinScene>
      <div className="pointer-events-none absolute left-3 top-3 rounded-lg bg-black/65 px-3 py-2 text-xs text-zinc-200 backdrop-blur">
        <div className="font-medium text-zinc-100">3D twin</div>
        <div data-testid="arm-twin-pose" className="mt-1 text-zinc-300">
          {formatPose(pose)}
        </div>
      </div>
      {(onJointJog || onPoseMove) && (
        <div className="absolute right-3 top-3 flex max-w-56 flex-col gap-2">
          {onJointJog && (
            <div className="rounded-lg bg-black/65 p-2 text-xs text-zinc-200 backdrop-blur">
              <div className="mb-2 font-medium text-zinc-100">Joint gizmo</div>
              <div className="flex flex-col gap-2">
                {states.map((state) => (
                  <button
                    key={state.name}
                    type="button"
                    data-testid={`arm-twin-jog-${state.name}`}
                    onPointerDown={(event) => {
                      jointDragRef.current = {
                        joint: state.index,
                        totalDx: 0,
                        lastX: event.clientX,
                      };
                    }}
                    className="pointer-events-auto rounded-md border border-zinc-700 bg-zinc-900/80 px-2 py-1 text-left text-[11px] text-zinc-100 hover:bg-zinc-800"
                  >
                    Drag {state.name}
                  </button>
                ))}
              </div>
            </div>
          )}
          {onPoseMove && pose && (
            <div className="rounded-lg bg-black/65 p-2 text-xs text-zinc-200 backdrop-blur">
              <div className="mb-2 font-medium text-zinc-100">TCP gizmo</div>
              <button
                type="button"
                data-testid="arm-twin-tcp-pad"
                onPointerDown={(event) => {
                  tcpDragRef.current = {
                    startX: event.clientX,
                    startY: event.clientY,
                    totalDx: 0,
                    totalDy: 0,
                    lastX: event.clientX,
                    lastY: event.clientY,
                  };
                }}
                className="pointer-events-auto flex h-24 w-24 items-center justify-center rounded-lg border border-dashed border-zinc-600 bg-zinc-900/80 text-[11px] text-zinc-300 hover:bg-zinc-800"
              >
                Drag TCP
              </button>
            </div>
          )}
        </div>
      )}
      <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-2">
        {states.map((state) => (
          <span
            key={state.name}
            data-testid={`arm-twin-joint-${state.name}`}
            className="rounded-full border border-black/30 px-2 py-1 text-[11px] font-medium text-black"
            style={{ backgroundColor: ARM_TWIN_COLORS[state.limitState] }}
          >
            {state.name} {state.degrees.toFixed(0)}°
          </span>
        ))}
      </div>
    </div>
  );
}

export default ArmTwin;
