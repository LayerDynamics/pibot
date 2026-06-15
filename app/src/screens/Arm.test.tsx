import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

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
    ageMs: 50,
    stale: false,
    loaded: true,
    error: null,
    fetch: async () => {},
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
});
