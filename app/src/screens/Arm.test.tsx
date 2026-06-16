import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useArmStore } from "../stores/armStore";
import { useConnectionStore } from "../stores/connectionStore";
import Arm from "./Arm";

const EP = { url: "http://localhost:9999", token: "t" };

/** Seed the store with a connected, enabled arm. `fetch` is stubbed to a no-op so the screen's
 * poll never makes a real network call — this test exercises rendering given store state; the
 * store's fetch/motion behavior is covered in armStore.test.ts. */
function seed(over: Partial<ReturnType<typeof useArmStore.getState>> = {}): void {
  useArmStore.setState({
    enabled: true,
    numJoints: 2,
    positions: { "0": 10, "1": 20 },
    homed: { "0": true, "1": false },
    estopped: false,
    gripper: { deg: 25, tool: false },
    pose: { x: 0.5, y: 0, z: 0.3, rx: 0, ry: 0, rz: 0 },
    ageMs: 50,
    stale: false,
    loaded: true,
    poses: [],
    programs: [],
    programStatus: null,
    error: null,
    fetch: async () => {},
    fetchPoses: async () => {},
    poseSave: async () => {},
    fetchPrograms: async () => {},
    saveProgram: async () => {},
    runProgram: async () => {},
    stopProgram: async () => {},
    ...over,
  });
}

beforeEach(() => {
  useArmStore.getState().reset();
  useConnectionStore.getState().setState("connected", "bot");
});

afterEach(() => {
  // Unmount first (clears the screen's poll interval and store subscription) so the store
  // resets below don't re-render a stale, still-mounted component outside act.
  cleanup();
  useConnectionStore.getState().setState("disconnected");
  useArmStore.getState().reset();
});

describe("Arm screen controls", () => {
  it("renders jog/home/move controls + E-Stop for a connected, enabled arm", () => {
    seed();
    render(<Arm ep={EP} />);

    expect(screen.getByTestId("arm-estop")).toBeInTheDocument();
    expect(screen.getByTestId("arm-jog-pos-0")).toBeInTheDocument();
    expect(screen.getByTestId("arm-jog-neg-0")).toBeInTheDocument();
    expect(screen.getByTestId("arm-home-1")).toBeInTheDocument();
    // The homed indicator reflects the per-joint telemetry flag.
    expect(screen.getByTestId("arm-homed-0")).toHaveTextContent("homed");
    expect(screen.getByTestId("arm-homed-1")).toHaveTextContent("not homed");
  });

  it("disables jog while e-stop is latched", () => {
    seed({ estopped: true });
    render(<Arm ep={EP} />);

    expect(screen.getByTestId("arm-estop-latched")).toBeInTheDocument();
    expect(screen.getByTestId("arm-jog-pos-0")).toBeDisabled();
    expect(screen.getByTestId("arm-jog-neg-0")).toBeDisabled();
  });

  it("disables the Go (absolute move) button until the joint is homed", () => {
    seed();
    render(<Arm ep={EP} />);

    expect(screen.getByTestId("arm-goto-0")).toBeEnabled(); // J0 homed
    expect(screen.getByTestId("arm-goto-1")).toBeDisabled(); // J1 not homed
  });

  it("jogs on pointer-down and stops on pointer-up, leave, AND cancel (touch safety)", () => {
    const jog = vi.fn().mockResolvedValue(undefined);
    seed({ jog });
    render(<Arm ep={EP} />);

    const plus = screen.getByTestId("arm-jog-pos-0");
    fireEvent.pointerDown(plus);
    expect(jog).toHaveBeenLastCalledWith(EP, 0, 15); // +JOG_DPS
    fireEvent.pointerUp(plus);
    expect(jog).toHaveBeenLastCalledWith(EP, 0, 0); // stop

    // A pointer-cancel (touch/scroll/system gesture interrupt) must also stop — else the joint
    // would keep jogging with no release event.
    fireEvent.pointerDown(plus);
    expect(jog).toHaveBeenLastCalledWith(EP, 0, 15);
    fireEvent.pointerCancel(plus);
    expect(jog).toHaveBeenLastCalledWith(EP, 0, 0);

    // pointer-leave stops too, and the − button jogs the other direction.
    const minus = screen.getByTestId("arm-jog-neg-1");
    fireEvent.pointerDown(minus);
    expect(jog).toHaveBeenLastCalledWith(EP, 1, -15);
    fireEvent.pointerLeave(minus);
    expect(jog).toHaveBeenLastCalledWith(EP, 1, 0);
  });

  it("renders the gripper control and drives grip/tool actions", () => {
    const grip = vi.fn().mockResolvedValue(undefined);
    const tool = vi.fn().mockResolvedValue(undefined);
    seed({ grip, tool, gripper: { deg: 25, tool: true } });
    render(<Arm ep={EP} />);

    // Readout reflects the telemetry gripper state.
    expect(screen.getByTestId("arm-gripper-readout")).toHaveTextContent("25° · tool on");

    fireEvent.click(screen.getByTestId("arm-grip-open"));
    expect(grip).toHaveBeenLastCalledWith(EP, 0);
    fireEvent.click(screen.getByTestId("arm-grip-close"));
    expect(grip).toHaveBeenLastCalledWith(EP, 180);
    // Tool toggles the opposite of the current (on) state.
    fireEvent.click(screen.getByTestId("arm-tool-toggle"));
    expect(tool).toHaveBeenLastCalledWith(EP, false);
  });

  it("disables gripper controls while e-stop is latched", () => {
    seed({ estopped: true });
    render(<Arm ep={EP} />);

    expect(screen.getByTestId("arm-grip-open")).toBeDisabled();
    expect(screen.getByTestId("arm-tool-toggle")).toBeDisabled();
  });

  it("shows the FK end-effector pose when present, and hides it when null", () => {
    seed({ pose: { x: 0.5, y: 0, z: 0.3, rx: 0, ry: 0, rz: 0 } });
    const { unmount } = render(<Arm ep={EP} />);
    expect(screen.getByTestId("arm-ee-pose")).toHaveTextContent("x 500");
    expect(screen.getByTestId("arm-ee-pose")).toHaveTextContent("z 300");
    unmount();

    seed({ pose: null });
    render(<Arm ep={EP} />);
    expect(screen.queryByTestId("arm-ee-pose")).toBeNull();
  });

  it("renders the Cartesian move panel only when a pose is present, and drives moveCartesian", () => {
    const moveCartesian = vi.fn().mockResolvedValue(undefined);
    seed({ moveCartesian });
    render(<Arm ep={EP} />);

    fireEvent.change(screen.getByTestId("arm-xyz-x"), { target: { value: "300" } });
    fireEvent.change(screen.getByTestId("arm-xyz-y"), { target: { value: "0" } });
    fireEvent.change(screen.getByTestId("arm-xyz-z"), { target: { value: "400" } });
    fireEvent.change(screen.getByTestId("arm-xyz-seconds"), { target: { value: "1.5" } });
    fireEvent.click(screen.getByTestId("arm-xyz-go"));

    // mm -> m conversion happens at the UI boundary.
    expect(moveCartesian).toHaveBeenLastCalledWith(EP, 0.3, 0, 0.4, 1.5);
  });

  it("hides the Cartesian panel when no FK pose is available", () => {
    seed({ pose: null });
    render(<Arm ep={EP} />);
    expect(screen.queryByTestId("arm-cartesian")).toBeNull();
  });

  it("disables the Cartesian Go button while e-stop is latched", () => {
    seed({ estopped: true });
    render(<Arm ep={EP} />);
    expect(screen.getByTestId("arm-xyz-go")).toBeDisabled();
  });

  it("renders the teach/playback panel, saves an ordered multi-step program, and shows progress", () => {
    const poseSave = vi.fn().mockResolvedValue(undefined);
    const saveProgram = vi.fn().mockResolvedValue(undefined);
    const runProgram = vi.fn().mockResolvedValue(undefined);
    const stopProgram = vi.fn().mockResolvedValue(undefined);
    seed({
      poseSave,
      saveProgram,
      runProgram,
      stopProgram,
      poses: [{ name: "ready", joints: { "0": 10, "1": 20 }, created: 1 }],
      programs: [{ name: "pick", steps: [{ kind: "moveJ", pose: "ready", seconds: 1 }] }],
      programStatus: {
        name: "pick",
        state: "running",
        current_step: 2,
        total_steps: 3,
        current_kind: "wait",
        message: null,
      },
    });
    render(<Arm ep={EP} />);

    fireEvent.change(screen.getByTestId("arm-pose-name"), { target: { value: "ready" } });
    fireEvent.click(screen.getByTestId("arm-pose-save"));
    expect(poseSave).toHaveBeenLastCalledWith(EP, "ready");

    expect(screen.getByTestId("arm-pose-row-ready")).toBeInTheDocument();
    expect(screen.getByTestId("arm-program-row-pick")).toBeInTheDocument();
    expect(screen.getByTestId("arm-program-progress")).toHaveTextContent("2 / 3");
    expect(screen.getByTestId("arm-program-progress")).toHaveTextContent("wait");

    fireEvent.change(screen.getByTestId("arm-program-name"), { target: { value: "demo" } });
    fireEvent.change(screen.getByTestId("arm-program-step-pose"), { target: { value: "ready" } });
    fireEvent.change(screen.getByTestId("arm-program-step-seconds"), { target: { value: "1.5" } });
    fireEvent.click(screen.getByTestId("arm-program-add-step"));

    fireEvent.change(screen.getByTestId("arm-program-step-kind"), { target: { value: "wait" } });
    fireEvent.change(screen.getByTestId("arm-program-step-seconds"), { target: { value: "0.25" } });
    fireEvent.click(screen.getByTestId("arm-program-add-step"));
    fireEvent.click(screen.getByTestId("arm-program-step-up-1"));
    fireEvent.click(screen.getByTestId("arm-program-save"));

    expect(saveProgram).toHaveBeenLastCalledWith(EP, {
      name: "demo",
      steps: [
        { kind: "wait", seconds: 0.25 },
        { kind: "moveJ", pose: "ready", seconds: 1.5 },
      ],
    });

    fireEvent.click(screen.getByTestId("arm-program-run-pick"));
    expect(runProgram).toHaveBeenLastCalledWith(EP, "pick");
    fireEvent.click(screen.getByTestId("arm-program-stop"));
    expect(stopProgram).toHaveBeenLastCalledWith(EP);
  });
});
