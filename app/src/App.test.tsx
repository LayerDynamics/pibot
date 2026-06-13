import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("App shell", () => {
  it("renders a top bar with a connection indicator and an always-visible e-stop button", () => {
    render(<App />);
    // The e-stop must always be reachable (SPEC-3 FR-8) — present from first paint.
    expect(
      screen.getByRole("button", { name: /e-?stop/i }),
    ).toBeInTheDocument();
    // The connection state lives in the persistent top bar.
    expect(screen.getByTestId("connection-indicator")).toBeInTheDocument();
  });

  it("navigates between all five operator screens", () => {
    render(<App />);
    // Dashboard is the default screen (no telemetry yet -> empty state).
    expect(screen.getByTestId("dashboard-empty")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Drive" }));
    expect(screen.getByTestId("drive-screen")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Autonomy" }));
    expect(screen.getByTestId("autonomy-screen")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Data" }));
    expect(screen.getByTestId("data-screen")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Provisioning" }));
    expect(screen.getByTestId("provisioning-screen")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dashboard" }));
    expect(screen.getByTestId("dashboard-empty")).toBeInTheDocument();
  });
});
