import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api/client", () => ({
  mcEndpoint: vi.fn(async () => ({ url: "http://127.0.0.1:1", token: "t" })),
  listRobots: vi.fn(async () => [
    { alias: "pibot", address: "192.168.100.2", ip: "192.168.100.2", hostname: "", user: null, link: "", pi: true },
  ]),
  connectRobot: vi.fn(async () => undefined),
  disconnectRobot: vi.fn(async () => undefined),
  openTelemetry: vi.fn(() => ({ close: vi.fn() })),
}));

import * as client from "../lib/api/client";
import { useConnectionStore } from "../stores/connectionStore";
import ConnectBar from "./ConnectBar";

beforeEach(() => {
  useConnectionStore.setState({ state: "disconnected", robot: null, error: null });
  vi.clearAllMocks();
});

describe("ConnectBar", () => {
  it("loads inventory and connects + opens the telemetry stream", async () => {
    render(<ConnectBar />);
    await screen.findByRole("option", { name: /pibot/ });

    await userEvent.click(screen.getByRole("button", { name: /^connect$/i }));

    await waitFor(() => {
      expect(client.connectRobot).toHaveBeenCalledWith(expect.anything(), "pibot");
      expect(client.openTelemetry).toHaveBeenCalledTimes(1);
      expect(useConnectionStore.getState().state).toBe("connected");
      expect(useConnectionStore.getState().robot).toBe("pibot");
    });
  });
});
