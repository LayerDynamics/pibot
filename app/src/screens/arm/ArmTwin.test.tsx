import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { createEvent, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ArmTwin, ArmTwinScene } from "./ArmTwin";
import {
  ARM_TWIN_COLORS,
  ARM_URDF_PATH,
  applyJointStatesToRobot,
  buildTwinJointStates,
  parseArmTwinModel,
} from "./armTwinModel";

vi.mock("@react-three/fiber", () => ({
  Canvas: ({ children }: { children: ReactNode }) => (
    <div data-testid="arm-twin-canvas">{children}</div>
  ),
}));

vi.mock("@react-three/drei", () => ({
  OrbitControls: () => <div data-testid="arm-twin-orbit" />,
}));

function dispatchPointer(
  target: Element | Node | Document | Window,
  type: "pointerDown" | "pointerMove" | "pointerUp",
  init: { clientX?: number; clientY?: number; movementX?: number; movementY?: number } = {},
) {
  const event = createEvent[type](target, init);
  for (const [key, value] of Object.entries(init)) {
    Object.defineProperty(event, key, { value });
  }
  fireEvent(target, event);
}

describe("ArmTwin scene", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it("smoke-renders the three.js scene wrapper", () => {
    render(
      <ArmTwinScene>
        <div data-testid="arm-twin-inner" />
      </ArmTwinScene>,
    );

    expect(screen.getByTestId("arm-twin-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("arm-twin-orbit")).toBeInTheDocument();
    expect(screen.getByTestId("arm-twin-inner")).toBeInTheDocument();
  });

  it("parses the shipped public URDF to the expected joint set", () => {
    const urdfPath = resolve(process.cwd(), "public/arm/pibot_arm.urdf");
    expect(existsSync(urdfPath)).toBe(true);

    const urdfText = readFileSync(urdfPath, "utf8");
    const model = parseArmTwinModel(urdfText, ARM_URDF_PATH);

    expect(model.urdfPath).toBe(ARM_URDF_PATH);
    expect(model.joints.map((joint) => joint.name)).toEqual([
      "base",
      "shoulder",
      "elbow",
      "wrist_roll",
      "wrist_pitch",
      "tool_roll",
    ]);
  });

  it("maps telemetry onto the loaded joint order and flags near-limit joints", () => {
    const model = parseArmTwinModel(
      `<?xml version="1.0"?>
       <robot name="test">
         <link name="base_link" />
         <joint name="base" type="revolute">
           <parent link="base_link" />
           <child link="link_0" />
           <origin xyz="0 0 0" rpy="0 0 0" />
           <axis xyz="0 0 1" />
           <limit lower="-1.570796" upper="1.570796" effort="10" velocity="1" />
         </joint>
         <link name="link_0" />
         <joint name="shoulder" type="revolute">
           <parent link="link_0" />
           <child link="link_1" />
           <origin xyz="0 0 0.1" rpy="0 0 0" />
           <axis xyz="0 1 0" />
           <limit lower="-0.523599" upper="0.523599" effort="10" velocity="1" />
         </joint>
         <link name="link_1" />
         <joint name="tool" type="fixed">
           <parent link="link_1" />
           <child link="tool0" />
           <origin xyz="0 0 0.1" rpy="0 0 0" />
         </joint>
         <link name="tool0" />
       </robot>`,
      "/arm/test.urdf",
    );

    const states = buildTwinJointStates(model, { "0": 45, "1": 29 });
    expect(states.map((state) => state.name)).toEqual(["base", "shoulder"]);
    expect(states[0].radians).toBeCloseTo(Math.PI / 4, 5);
    expect(states[0].limitState).toBe("safe");
    expect(states[1].limitState).toBe("danger");

    const baseColor = vi.fn();
    const shoulderColor = vi.fn();
    const baseSetJointValue = vi.fn();
    const shoulderSetJointValue = vi.fn();
    applyJointStatesToRobot(
      {
        joints: {
          base: { setJointValue: baseSetJointValue },
          shoulder: { setJointValue: shoulderSetJointValue },
        },
        links: {
          link_0: { material: { color: { set: baseColor } } },
          link_1: { material: { color: { set: shoulderColor } } },
        },
      },
      states,
    );
    expect(baseSetJointValue).toHaveBeenCalledWith(states[0].radians);
    expect(shoulderSetJointValue).toHaveBeenCalledWith(states[1].radians);
    expect(baseColor).toHaveBeenCalledWith(ARM_TWIN_COLORS.safe);
    expect(shoulderColor).toHaveBeenCalledWith(ARM_TWIN_COLORS.danger);
  });

  it("falls back cleanly when the URDF path cannot be loaded", async () => {
    render(
      <ArmTwin
        positions={{}}
        pose={null}
        loadModel={async () => {
          throw new Error("404 not found");
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("arm-twin-fallback")).toHaveTextContent("Twin unavailable");
    });
  });

  it("drags the joint gizmo through jog callbacks and stops on release", async () => {
    const onJointJog = vi.fn();
    const onJointStop = vi.fn();
    render(
      <ArmTwin
        positions={{ "0": 10 }}
        pose={null}
        loadModel={async () =>
          parseArmTwinModel(
            `<?xml version="1.0"?>
             <robot name="test">
               <link name="base_link" />
               <joint name="base" type="revolute">
                 <parent link="base_link" />
                 <child link="link_0" />
                 <origin xyz="0 0 0" rpy="0 0 0" />
                 <axis xyz="0 0 1" />
                 <limit lower="-1.570796" upper="1.570796" effort="10" velocity="1" />
               </joint>
               <link name="link_0" />
               <joint name="tool" type="fixed">
                 <parent link="link_0" />
                 <child link="tool0" />
                 <origin xyz="0 0 0.1" rpy="0 0 0" />
               </joint>
               <link name="tool0" />
             </robot>`,
            ARM_URDF_PATH,
          )
        }
        loadRobot={async () => ({ joints: {}, links: {} } as never)}
        onJointJog={onJointJog}
        onJointStop={onJointStop}
      />,
    );

    const handle = await screen.findByTestId("arm-twin-jog-base");
    dispatchPointer(handle, "pointerDown", { clientX: 100 });
    dispatchPointer(window, "pointerMove", { clientX: 160, movementX: 60 });
    expect(onJointJog).toHaveBeenCalledWith(0, expect.any(Number));
    dispatchPointer(window, "pointerUp");
    expect(onJointStop).toHaveBeenCalledWith(0);
  });

  it("drags the tcp pad through a relative cartesian move callback", async () => {
    const onPoseMove = vi.fn();
    render(
      <ArmTwin
        positions={{}}
        pose={{ x: 0.3, y: 0.1, z: 0.4, rx: 0, ry: 0, rz: 0 }}
        loadModel={async () =>
          parseArmTwinModel(
            `<?xml version="1.0"?>
             <robot name="test">
               <link name="base_link" />
               <joint name="base" type="revolute">
                 <parent link="base_link" />
                 <child link="link_0" />
                 <origin xyz="0 0 0" rpy="0 0 0" />
                 <axis xyz="0 0 1" />
                 <limit lower="-1.570796" upper="1.570796" effort="10" velocity="1" />
               </joint>
               <link name="link_0" />
               <joint name="tool" type="fixed">
                 <parent link="link_0" />
                 <child link="tool0" />
                 <origin xyz="0 0 0.1" rpy="0 0 0" />
               </joint>
               <link name="tool0" />
             </robot>`,
            ARM_URDF_PATH,
          )
        }
        loadRobot={async () => ({ joints: {}, links: {} } as never)}
        onPoseMove={onPoseMove}
      />,
    );

    const pad = await screen.findByTestId("arm-twin-tcp-pad");
    dispatchPointer(pad, "pointerDown", { clientX: 100, clientY: 100 });
    dispatchPointer(window, "pointerMove", {
      clientX: 120,
      clientY: 80,
      movementX: 20,
      movementY: -20,
    });
    dispatchPointer(window, "pointerUp", { clientX: 120, clientY: 80 });
    expect(onPoseMove).toHaveBeenCalledWith({ dxMm: 20, dyMm: 20 });
  });
});
