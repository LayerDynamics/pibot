import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ConfirmModal from "./ConfirmModal";
import type { OpsJob } from "../stores/opsStore";

const BASE_JOB: OpsJob = {
  id: "job-1",
  kind: "flash",
  args: {},
  dry_run: true,
  confirmed: false,
  guard_passed: false,
  status: "awaiting-confirm",
  progress: 0,
  log: ["[dry-run] flash /dev/sda"],
};

const NON_DESTRUCTIVE_JOB: OpsJob = { ...BASE_JOB, kind: "deploy" };

describe("ConfirmModal — destructive (flash)", () => {
  it("renders the modal with guard checkbox", () => {
    render(
      <ConfirmModal
        job={BASE_JOB}
        guardAcknowledged={false}
        onAcknowledgeGuard={vi.fn()}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByTestId("confirm-modal")).toBeDefined();
    expect(screen.getByTestId("guard-checkbox")).toBeDefined();
  });

  it("Confirm button is disabled when guard not acknowledged", () => {
    render(
      <ConfirmModal
        job={BASE_JOB}
        guardAcknowledged={false}
        onAcknowledgeGuard={vi.fn()}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const confirmBtn = screen.getByTestId("modal-confirm") as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);
  });

  it("Confirm button is enabled when guard acknowledged", () => {
    render(
      <ConfirmModal
        job={BASE_JOB}
        guardAcknowledged={true}
        onAcknowledgeGuard={vi.fn()}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const confirmBtn = screen.getByTestId("modal-confirm") as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(false);
  });

  it("clicking Confirm calls onConfirm", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmModal
        job={BASE_JOB}
        guardAcknowledged={true}
        onAcknowledgeGuard={vi.fn()}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("modal-confirm"));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("clicking Cancel calls onCancel", () => {
    const onCancel = vi.fn();
    render(
      <ConfirmModal
        job={BASE_JOB}
        guardAcknowledged={false}
        onAcknowledgeGuard={vi.fn()}
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByTestId("modal-cancel"));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("clicking the checkbox calls onAcknowledgeGuard", () => {
    const onAck = vi.fn();
    render(
      <ConfirmModal
        job={BASE_JOB}
        guardAcknowledged={false}
        onAcknowledgeGuard={onAck}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("guard-checkbox"));
    expect(onAck).toHaveBeenCalledOnce();
  });
});

describe("ConfirmModal — non-destructive (deploy)", () => {
  it("does NOT render the guard checkbox", () => {
    render(
      <ConfirmModal
        job={NON_DESTRUCTIVE_JOB}
        guardAcknowledged={false}
        onAcknowledgeGuard={vi.fn()}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("guard-checkbox")).toBeNull();
  });

  it("Confirm button is enabled without guard acknowledgment", () => {
    render(
      <ConfirmModal
        job={NON_DESTRUCTIVE_JOB}
        guardAcknowledged={false}
        onAcknowledgeGuard={vi.fn()}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    const confirmBtn = screen.getByTestId("modal-confirm") as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(false);
  });
});
