import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTeleopStore } from "./teleopStore";

// Spy on the WebSocket send so we can verify frames without a real server.
const mockSend = vi.fn();

// Minimal WebSocket stub accepted by the store.
function makeWs(): WebSocket {
  return {
    readyState: WebSocket.OPEN,
    send: mockSend,
    close: vi.fn(),
  } as unknown as WebSocket;
}

beforeEach(() => {
  mockSend.mockClear();
  useTeleopStore.getState().reset();
});

describe("teleopStore", () => {
  it("starts with no keys and no ws", () => {
    const s = useTeleopStore.getState();
    expect(s.pressedKeys.size).toBe(0);
    expect(s.ws).toBeNull();
  });

  it("setWs stores the socket", () => {
    const ws = makeWs();
    useTeleopStore.getState().setWs(ws);
    expect(useTeleopStore.getState().ws).toBe(ws);
  });

  it("keyDown/keyUp update pressedKeys", () => {
    useTeleopStore.getState().keyDown("KeyW");
    expect(useTeleopStore.getState().pressedKeys.has("KeyW")).toBe(true);
    useTeleopStore.getState().keyUp("KeyW");
    expect(useTeleopStore.getState().pressedKeys.has("KeyW")).toBe(false);
  });

  it("keyDown emits a drive frame over the ws", () => {
    const ws = makeWs();
    useTeleopStore.getState().setWs(ws);
    useTeleopStore.getState().keyDown("KeyW");
    expect(mockSend).toHaveBeenCalledTimes(1);
    const frame = JSON.parse(mockSend.mock.calls[0][0] as string) as {
      cmd: string;
      args: { v: number; w: number };
    };
    expect(frame.cmd).toBe("drive");
    expect(frame.args.v).toBeGreaterThan(0);
  });

  it("keyUp sends stop when no keys remain", () => {
    const ws = makeWs();
    useTeleopStore.getState().setWs(ws);
    useTeleopStore.getState().keyDown("KeyW");
    mockSend.mockClear();
    useTeleopStore.getState().keyUp("KeyW");
    expect(mockSend).toHaveBeenCalledTimes(1);
    const frame = JSON.parse(mockSend.mock.calls[0][0] as string) as { cmd: string };
    expect(frame.cmd).toBe("stop");
  });

  it("Escape key sends stop and clears keys", () => {
    const ws = makeWs();
    useTeleopStore.getState().setWs(ws);
    useTeleopStore.getState().keyDown("KeyW");
    mockSend.mockClear();
    useTeleopStore.getState().keyDown("Escape");
    const frame = JSON.parse(mockSend.mock.calls[0][0] as string) as { cmd: string };
    expect(frame.cmd).toBe("stop");
    expect(useTeleopStore.getState().pressedKeys.size).toBe(0);
  });

  it("stop() sends stop frame and clears keys", () => {
    const ws = makeWs();
    useTeleopStore.getState().setWs(ws);
    useTeleopStore.getState().keyDown("KeyW");
    mockSend.mockClear();
    useTeleopStore.getState().stop();
    expect(mockSend).toHaveBeenCalledTimes(1);
    const frame = JSON.parse(mockSend.mock.calls[0][0] as string) as { cmd: string };
    expect(frame.cmd).toBe("stop");
    expect(useTeleopStore.getState().pressedKeys.size).toBe(0);
  });

  it("does not send if ws is null", () => {
    useTeleopStore.getState().keyDown("KeyW");
    expect(mockSend).not.toHaveBeenCalled();
  });

  it("ignores OS key-repeat: holding a key emits only one drive frame", () => {
    const ws = makeWs();
    useTeleopStore.getState().setWs(ws);
    useTeleopStore.getState().keyDown("KeyW");
    useTeleopStore.getState().keyDown("KeyW"); // browser fires keydown repeatedly while held
    useTeleopStore.getState().keyDown("KeyW");
    expect(mockSend).toHaveBeenCalledTimes(1);
  });
});
