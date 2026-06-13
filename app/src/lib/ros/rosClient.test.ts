import { describe, expect, it, vi } from "vitest";

// Capture the roslib objects the wrapper creates so we can assert on them.
const hoisted = vi.hoisted(() => ({
  topics: [] as Array<{ name: string; subscribe: ReturnType<typeof vi.fn>; publish: ReturnType<typeof vi.fn> }>,
  lastRos: null as { url: string; on: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn> } | null,
}));

vi.mock("roslib", () => {
  class Ros {
    url: string;
    on = vi.fn();
    close = vi.fn();
    constructor(opts: { url: string }) {
      // Mirror WKWebView: constructing a WebSocket with a rejected URL throws synchronously.
      if (opts.url === "ws://throws") {
        throw new DOMException("The string did not match the expected pattern.", "SyntaxError");
      }
      this.url = opts.url;
      hoisted.lastRos = this;
    }
  }
  class Topic {
    name: string;
    subscribe = vi.fn();
    publish = vi.fn();
    constructor(opts: { name: string }) {
      this.name = opts.name;
      hoisted.topics.push(this);
    }
  }
  return { Ros, Topic };
});

import { RosLink, rosbridgeUrl } from "./rosClient";

describe("rosClient", () => {
  it("derives the rosbridge url from a robot address", () => {
    expect(rosbridgeUrl("192.168.100.2")).toBe("ws://192.168.100.2:9090");
  });

  it("connects, subscribes the pibot topics, and reports status", () => {
    hoisted.topics.length = 0;
    const status: string[] = [];
    const link = new RosLink();
    link.connect("ws://robot:9090", { onStatus: (s) => status.push(s) });

    expect(status).toContain("connecting");
    expect(hoisted.lastRos?.url).toBe("ws://robot:9090");
    const names = hoisted.topics.map((t) => t.name);
    expect(names).toEqual(
      expect.arrayContaining([
        "/pibot/estop",
        "/pibot/telemetry",
        "/pibot/image/compressed",
        "/cmd_vel",
      ]),
    );
  });

  it("publishes a Twist on /cmd_vel when driving", () => {
    hoisted.topics.length = 0;
    const link = new RosLink();
    link.connect("ws://robot:9090", { onStatus: () => {} });
    const cmd = hoisted.topics.find((t) => t.name === "/cmd_vel");
    link.drive(0.5, -0.2);
    expect(cmd?.publish).toHaveBeenCalledTimes(1);
    const sent = cmd?.publish.mock.calls[0][0] as { linear: { x: number }; angular: { z: number } };
    expect(sent.linear.x).toBe(0.5);
    expect(sent.angular.z).toBe(-0.2);
  });

  it("reports error status (not an uncaught throw) when the socket URL is rejected", () => {
    // Regression: roslib's `new Ros` builds the WebSocket synchronously, so a malformed or
    // CSP-blocked URL threw a SyntaxError straight out of the click handler, freezing the
    // panel on "connecting". connect() must catch it and report "error".
    const status: string[] = [];
    const link = new RosLink();
    expect(() => link.connect("ws://throws", { onStatus: (s) => status.push(s) })).not.toThrow();
    expect(status).toContain("connecting");
    expect(status).toContain("error");
    expect(link.connected).toBe(false);
  });

  it("close() tears down the ros connection", () => {
    const link = new RosLink();
    link.connect("ws://robot:9090", { onStatus: () => {} });
    const ros = hoisted.lastRos;
    link.close();
    expect(ros?.close).toHaveBeenCalled();
    expect(link.connected).toBe(false);
  });
});
