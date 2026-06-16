import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ArmTelemetry } from "../lib/api/types";
import { useArmStore } from "./armStore";

const FAKE_EP = { url: "http://localhost:9999", token: "test-token" };

function jsonResponse(body: ArmTelemetry, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

beforeEach(() => {
  useArmStore.getState().reset();
  vi.restoreAllMocks();
});

describe("armStore.fetch", () => {
  it("starts disabled, unloaded, with no positions", () => {
    const s = useArmStore.getState();
    expect(s.enabled).toBe(false);
    expect(s.loaded).toBe(false);
    expect(s.positions).toEqual({});
    expect(s.error).toBeNull();
  });

  it("stores joint angles, homing, and latch state from an enabled snapshot", async () => {
    const body: ArmTelemetry = {
      ok: true,
      enabled: true,
      num_joints: 3,
      positions: { "0": 12.5, "1": -4.25, "2": 0 },
      homed: { "0": true, "1": false, "2": false },
      estopped: true,
      gripper: { deg: 30, tool: true },
      pose: { x: 0.5, y: 0.1, z: 0.3, rx: 0, ry: 0, rz: 0 },
      program: null,
      ts: 1000,
      age_ms: 120,
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(body));

    await useArmStore.getState().fetch(FAKE_EP);

    const s = useArmStore.getState();
    expect(s.enabled).toBe(true);
    expect(s.numJoints).toBe(3);
    expect(s.positions).toEqual({ "0": 12.5, "1": -4.25, "2": 0 });
    expect(s.homed).toEqual({ "0": true, "1": false, "2": false });
    expect(s.estopped).toBe(true);
    expect(s.gripper).toEqual({ deg: 30, tool: true });
    expect(s.pose).toEqual({ x: 0.5, y: 0.1, z: 0.3, rx: 0, ry: 0, rz: 0 });
    expect(s.loaded).toBe(true);
    expect(s.stale).toBe(false);
    expect(s.error).toBeNull();
  });

  it("marks the sample stale when age_ms exceeds the threshold", async () => {
    const body: ArmTelemetry = {
      ok: true,
      enabled: true,
      num_joints: 1,
      positions: { "0": 5 },
      homed: { "0": true },
      estopped: false,
      gripper: null,
      pose: null,
      program: null,
      ts: 1,
      age_ms: 1500,
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(body));

    await useArmStore.getState().fetch(FAKE_EP);

    expect(useArmStore.getState().stale).toBe(true);
  });

  it("reports a disabled arm as loaded-but-not-enabled", async () => {
    const body: ArmTelemetry = {
      ok: true,
      enabled: false,
      num_joints: 0,
      positions: {},
      homed: {},
      estopped: false,
      gripper: null,
      pose: null,
      program: null,
      ts: 0,
      age_ms: null,
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(body));

    await useArmStore.getState().fetch(FAKE_EP);

    const s = useArmStore.getState();
    expect(s.loaded).toBe(true);
    expect(s.enabled).toBe(false);
    expect(s.stale).toBe(false);
  });

  it("sets an error on a non-2xx response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => "not connected to robot",
    } as Response);

    await useArmStore.getState().fetch(FAKE_EP);

    expect(useArmStore.getState().error).toContain("503");
  });

  it("sets an error when fetch throws", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network down"));

    await useArmStore.getState().fetch(FAKE_EP);

    expect(useArmStore.getState().error).toContain("network down");
  });

  it("stores running program progress from telemetry", async () => {
    const body: ArmTelemetry = {
      ok: true,
      enabled: true,
      num_joints: 1,
      positions: { "0": 5 },
      homed: { "0": true },
      estopped: false,
      gripper: null,
      pose: null,
      program: {
        name: "pick",
        state: "running",
        current_step: 2,
        total_steps: 3,
        current_kind: "wait",
        message: null,
      },
      ts: 1,
      age_ms: 20,
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(body));

    await useArmStore.getState().fetch(FAKE_EP);

    expect(useArmStore.getState().programStatus).toEqual(body.program);
  });
});

function ackResponse(): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({ type: "ack" }),
    text: async () => '{"type":"ack"}',
  } as Response;
}

function jsonBody<T>(body: T, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

function nakResponse(reason: string): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({ type: "nak", reason }),
    text: async () => JSON.stringify({ type: "nak", reason }),
  } as Response;
}

/** Pull the (url, init) of the last fetch call. */
function lastCall(spy: { mock: { calls: unknown[][] } }): {
  url: string;
  body: unknown;
  method?: string;
} {
  const calls = spy.mock.calls;
  const [url, init] = calls[calls.length - 1] as [string, RequestInit];
  return {
    url,
    method: init?.method,
    body: init?.body ? JSON.parse(init.body as string) : undefined,
  };
}

describe("armStore motion actions", () => {
  it("jog POSTs joint+dps to /api/arm/jog", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(ackResponse());
    await useArmStore.getState().jog(FAKE_EP, 2, 30);
    const call = lastCall(spy);
    expect(call.url).toContain("/api/arm/jog");
    expect(call.method).toBe("POST");
    expect(call.body).toEqual({ joint: 2, dps: 30 });
    expect(useArmStore.getState().error).toBeNull();
  });

  it("moveJoint omits speed by default and includes it when given", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(ackResponse());
    await useArmStore.getState().moveJoint(FAKE_EP, 1, 45);
    expect(lastCall(spy).body).toEqual({ joint: 1, deg: 45 });
    await useArmStore.getState().moveJoint(FAKE_EP, 1, 45, 20);
    expect(lastCall(spy).body).toEqual({ joint: 1, deg: 45, speed: 20 });
  });

  it("home POSTs the joint to /api/arm/home", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(ackResponse());
    await useArmStore.getState().home(FAKE_EP, 0);
    const call = lastCall(spy);
    expect(call.url).toContain("/api/arm/home");
    expect(call.body).toEqual({ joint: 0 });
  });

  it("estop POSTs to /api/arm/estop and latches the store", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(ackResponse());
    await useArmStore.getState().estop(FAKE_EP);
    expect(lastCall(spy).url).toContain("/api/arm/estop");
    expect(useArmStore.getState().estopped).toBe(true);
  });

  it("clearEstop POSTs to /api/arm/clear_estop and unlatches", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(ackResponse());
    await useArmStore.getState().estop(FAKE_EP);
    expect(useArmStore.getState().estopped).toBe(true);
    await useArmStore.getState().clearEstop(FAKE_EP);
    expect(useArmStore.getState().estopped).toBe(false);
  });

  it("enable POSTs the on flag to /api/arm/enable", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(ackResponse());
    await useArmStore.getState().enable(FAKE_EP, false);
    const call = lastCall(spy);
    expect(call.url).toContain("/api/arm/enable");
    expect(call.body).toEqual({ on: false });
  });

  it("grip POSTs the angle to /api/arm/grip", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(ackResponse());
    await useArmStore.getState().grip(FAKE_EP, 42);
    const call = lastCall(spy);
    expect(call.url).toContain("/api/arm/grip");
    expect(call.body).toEqual({ deg: 42 });
  });

  it("tool POSTs the on flag to /api/arm/tool", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(ackResponse());
    await useArmStore.getState().tool(FAKE_EP, true);
    const call = lastCall(spy);
    expect(call.url).toContain("/api/arm/tool");
    expect(call.body).toEqual({ on: true });
  });

  it("moveCartesian POSTs position+seconds to /api/arm/move-cartesian, orientation defaults to 0", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(ackResponse());
    await useArmStore.getState().moveCartesian(FAKE_EP, 0.3, 0.0, 0.4, 1.5);
    const call = lastCall(spy);
    expect(call.url).toContain("/api/arm/move-cartesian");
    expect(call.method).toBe("POST");
    expect(call.body).toEqual({ x: 0.3, y: 0.0, z: 0.4, seconds: 1.5, rx: 0, ry: 0, rz: 0 });
  });

  it("moveCartesian includes a given orientation", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(ackResponse());
    await useArmStore.getState().moveCartesian(FAKE_EP, 0.1, 0.2, 0.3, 1.0, {
      rx: 0.1,
      ry: 0.2,
      rz: 0.3,
    });
    expect(lastCall(spy).body).toEqual({
      x: 0.1,
      y: 0.2,
      z: 0.3,
      seconds: 1.0,
      rx: 0.1,
      ry: 0.2,
      rz: 0.3,
    });
  });

  it("moveCartesian surfaces an 'unreachable' nak as an error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(nakResponse("unreachable: pose ..."));
    await useArmStore.getState().moveCartesian(FAKE_EP, 10, 0, 0, 1.0);
    expect(useArmStore.getState().error).toContain("unreachable");
  });

  it("surfaces a host-gate nak as an error and does not latch on a refused estop", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(nakResponse("joint 0 not homed"));
    await useArmStore.getState().moveJoint(FAKE_EP, 0, 10);
    expect(useArmStore.getState().error).toContain("not homed");
  });

  it("does not latch when the estop POST fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => "not connected",
      json: async () => ({}),
    } as Response);
    await useArmStore.getState().estop(FAKE_EP);
    expect(useArmStore.getState().estopped).toBe(false);
    expect(useArmStore.getState().error).toContain("503");
  });

  it("poseSave POSTs the name to /api/arm/poses", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonBody({ name: "ready", joints: { "0": 1 } }, 201));
    await useArmStore.getState().poseSave(FAKE_EP, "ready");
    const call = lastCall(spy);
    expect(call.url).toContain("/api/arm/poses");
    expect(call.body).toEqual({ name: "ready" });
  });

  it("fetchPoses stores the returned pose list", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonBody({
        poses: [
          { name: "home", joints: { "0": 0 }, created: 1 },
          { name: "ready", joints: { "0": 10 }, created: 2 },
        ],
      }),
    );
    await useArmStore.getState().fetchPoses(FAKE_EP);
    expect(useArmStore.getState().poses.map((pose) => pose.name)).toEqual(["home", "ready"]);
  });

  it("saveProgram POSTs the program and fetchPrograms stores the returned list", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonBody({ name: "pick", steps: [{ kind: "wait", seconds: 0.1 }] }, 201),
      )
      .mockResolvedValueOnce(
        jsonBody({
          programs: [{ name: "pick", steps: [{ kind: "wait", seconds: 0.1 }] }],
        }),
      );
    await useArmStore
      .getState()
      .saveProgram(FAKE_EP, { name: "pick", steps: [{ kind: "wait", seconds: 0.1 }] });
    expect(lastCall(spy).url).toContain("/api/arm/programs");

    await useArmStore.getState().fetchPrograms(FAKE_EP);
    expect(useArmStore.getState().programs.map((program) => program.name)).toEqual(["pick"]);
  });

  it("runProgram and stopProgram POST to the right routes", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonBody({ running: true, name: "pick" }, 202))
      .mockResolvedValueOnce(jsonBody({ stopped: true }));
    await useArmStore.getState().runProgram(FAKE_EP, "pick");
    expect(lastCall(spy).url).toContain("/api/arm/programs/pick/run");
    await useArmStore.getState().stopProgram(FAKE_EP);
    expect(lastCall(spy).url).toContain("/api/arm/programs/stop");
  });
});
