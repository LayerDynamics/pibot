import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useGamepadStore } from "./gamepadStore";
import { useTeleopStore } from "./teleopStore";

const mockSend = vi.fn();

function makeWs(): WebSocket {
  return { readyState: WebSocket.OPEN, send: mockSend, close: vi.fn() } as unknown as WebSocket;
}

// Controllable fake gamepad. gamepadMap reads axes[1] (forward) and axes[2] (turn).
let axes: number[] = [0, 0, 0, 0];
function setAxes(a: number[]): void {
  axes = a;
}
function fakePad(): Gamepad {
  return {
    connected: true,
    axes,
    buttons: [],
    id: "test",
    index: 0,
    mapping: "standard",
    timestamp: 0,
  } as unknown as Gamepad;
}

// requestAnimationFrame control: capture the scheduled callback and run it manually per "tick"
// so the poll loop is deterministic. start() runs poll #1 synchronously and schedules the next.
let rafCb: FrameRequestCallback | null = null;
function tick(): void {
  const cb = rafCb;
  rafCb = null;
  cb?.(0);
}

beforeEach(() => {
  mockSend.mockClear();
  axes = [0, 0, 0, 0];
  rafCb = null;
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback): number => {
    rafCb = cb;
    return 1;
  });
  vi.stubGlobal("cancelAnimationFrame", () => {});
  vi.stubGlobal("navigator", { getGamepads: () => [fakePad()] });
  useTeleopStore.getState().reset();
  useTeleopStore.getState().setWs(makeWs());
  useGamepadStore.getState().stop();
});

afterEach(() => {
  useGamepadStore.getState().stop();
  vi.unstubAllGlobals();
});

describe("gamepadStore", () => {
  it("emits one frame for a held stick, not one per animation frame", () => {
    setAxes([0, -0.8, 0, 0]); // forward
    useGamepadStore.getState().start(); // poll #1 -> drive
    tick(); // poll #2 -> unchanged, no send
    tick(); // poll #3 -> unchanged, no send
    expect(mockSend).toHaveBeenCalledTimes(1);
    expect((JSON.parse(mockSend.mock.calls[0][0] as string) as { cmd: string }).cmd).toBe("drive");
  });

  it("emits a new frame when the stick moves", () => {
    setAxes([0, -0.8, 0, 0]);
    useGamepadStore.getState().start(); // drive
    expect(mockSend).toHaveBeenCalledTimes(1);
    setAxes([0, 0, 0, 0]); // back to neutral
    tick(); // change -> stop
    expect(mockSend).toHaveBeenCalledTimes(2);
    expect((JSON.parse(mockSend.mock.calls[1][0] as string) as { cmd: string }).cmd).toBe("stop");
  });

  it("re-sends after the keyboard yields control (no stale suppression)", () => {
    setAxes([0, -0.8, 0, 0]);
    useGamepadStore.getState().start(); // poll #1 -> drive
    expect(mockSend).toHaveBeenCalledTimes(1);
    // Keyboard takes priority: the gamepad must yield AND forget its last value.
    useTeleopStore.setState({ pressedKeys: new Set(["KeyW"]) });
    tick(); // poll #2 -> yields, resets last (v, w)
    expect(mockSend).toHaveBeenCalledTimes(1);
    // Release the keyboard: the gamepad resumes; the same stick must re-send, not be suppressed.
    useTeleopStore.setState({ pressedKeys: new Set() });
    tick(); // poll #3 -> resumes -> drive again
    expect(mockSend).toHaveBeenCalledTimes(2);
  });
});
