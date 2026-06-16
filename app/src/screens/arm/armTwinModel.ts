import { Material, Mesh } from "three";

const RAD_TO_DEG = 180 / Math.PI;
const DEG_TO_RAD = Math.PI / 180;
const LIMIT_WARNING_RATIO = 0.15;
const LIMIT_DANGER_RATIO = 0.05;

export const ARM_URDF_PATH = "/arm/pibot_arm.urdf";
export const ARM_TWIN_COLORS = {
  safe: "#60a5fa",
  warning: "#f59e0b",
  danger: "#ef4444",
} as const;

export type LimitState = keyof typeof ARM_TWIN_COLORS;

export interface ArmTwinJoint {
  name: string;
  index: number;
  minDeg: number;
  maxDeg: number;
  linkName: string;
}

export interface ArmTwinModel {
  urdfPath: string;
  joints: ArmTwinJoint[];
}

export interface TwinJointState extends ArmTwinJoint {
  degrees: number;
  radians: number;
  limitState: LimitState;
}

type TwinLinkLike = {
  material?: { color?: { set: (value: string) => void } };
  traverse?: (fn: (node: unknown) => void) => void;
};

export type TwinRobotLike = {
  joints: Record<string, { setJointValue: (value: number) => unknown }>;
  links: Record<string, TwinLinkLike>;
};

export function parseArmTwinModel(urdfText: string, urdfPath: string): ArmTwinModel {
  const doc = new DOMParser().parseFromString(urdfText, "application/xml");
  const robot = doc.querySelector("robot");
  if (!robot) throw new Error("invalid URDF: missing <robot>");

  const joints = Array.from(robot.querySelectorAll("joint"))
    .filter((joint) => {
      const type = joint.getAttribute("type");
      return type === "revolute" || type === "continuous";
    })
    .map((joint, index) => {
      const name = joint.getAttribute("name");
      const limit = joint.querySelector("limit");
      const child = joint.querySelector("child");
      if (!name || !limit || !child) throw new Error("invalid URDF joint definition");
      const lower = Number.parseFloat(limit.getAttribute("lower") ?? "");
      const upper = Number.parseFloat(limit.getAttribute("upper") ?? "");
      const linkName = child.getAttribute("link");
      if (Number.isNaN(lower) || Number.isNaN(upper) || !linkName) {
        throw new Error(`invalid URDF joint limits for ${name}`);
      }
      return {
        name,
        index,
        minDeg: lower * RAD_TO_DEG,
        maxDeg: upper * RAD_TO_DEG,
        linkName,
      };
    });

  if (joints.length === 0) throw new Error("invalid URDF: no revolute joints");
  return { urdfPath, joints };
}

export async function loadArmTwinModel(
  urdfPath: string = ARM_URDF_PATH,
  fetchImpl: typeof fetch = fetch,
): Promise<ArmTwinModel> {
  const response = await fetchImpl(urdfPath);
  if (!response.ok) throw new Error(`URDF fetch failed (${response.status})`);
  return parseArmTwinModel(await response.text(), urdfPath);
}

export function jointLimitState(degrees: number, minDeg: number, maxDeg: number): LimitState {
  const margin = Math.min(degrees - minDeg, maxDeg - degrees);
  const span = Math.max(1, maxDeg - minDeg);
  if (margin <= Math.max(2, span * LIMIT_DANGER_RATIO)) return "danger";
  if (margin <= Math.max(5, span * LIMIT_WARNING_RATIO)) return "warning";
  return "safe";
}

export function buildTwinJointStates(
  model: ArmTwinModel,
  positions: Record<string, number>,
): TwinJointState[] {
  return model.joints.map((joint) => {
    const degrees = positions[String(joint.index)] ?? 0;
    return {
      ...joint,
      degrees,
      radians: degrees * DEG_TO_RAD,
      limitState: jointLimitState(degrees, joint.minDeg, joint.maxDeg),
    };
  });
}

function setMaterialColor(
  material: Material | { color?: { set: (value: string) => void } },
  color: string,
): void {
  if ("color" in material && material.color) material.color.set(color);
}

function cloneMeshMaterials(node: Mesh): void {
  if (node.userData.armTwinOwnMaterial || !node.material) return;
  node.material = Array.isArray(node.material)
    ? node.material.map((material) => material.clone())
    : node.material.clone();
  node.userData.armTwinOwnMaterial = true;
}

function setObjectColor(target: TwinLinkLike | undefined, color: string): void {
  if (!target) return;
  if (target.traverse) {
    target.traverse((node: unknown) => {
      if (!(node instanceof Mesh)) return;
      cloneMeshMaterials(node);
      const material = node.material;
      if (Array.isArray(material)) material.forEach((entry) => setMaterialColor(entry, color));
      else setMaterialColor(material, color);
    });
    return;
  }
  if (target.material) setMaterialColor(target.material, color);
}

export function applyJointStatesToRobot(robot: TwinRobotLike, states: TwinJointState[]): void {
  for (const state of states) {
    robot.joints[state.name]?.setJointValue(state.radians);
    setObjectColor(robot.links[state.linkName], ARM_TWIN_COLORS[state.limitState]);
  }
}
