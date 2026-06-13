import { beforeEach, describe, expect, it, vi } from "vitest";

import type { McEndpoint } from "../lib/api/types";
import type { OpsJob } from "./opsStore";
import { useOpsStore } from "./opsStore";

const EP: McEndpoint = { url: "http://mc", token: "tok" };

const PREVIEW_JOB: OpsJob = {
  id: "job-1",
  kind: "flash",
  args: {},
  dry_run: true,
  confirmed: false,
  guard_passed: false,
  status: "awaiting-confirm",
  progress: 0,
  log: ["[dry-run] flash"],
};

const DONE_JOB: OpsJob = { ...PREVIEW_JOB, status: "done", confirmed: true, guard_passed: true };

beforeEach(() => {
  useOpsStore.setState({ job: null, confirmPending: false, guardAcknowledged: false, error: null });
  vi.restoreAllMocks();
});

describe("submit", () => {
  it("posts to /api/ops/{kind} and sets the job", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve(PREVIEW_JOB) }),
      ),
    );
    await useOpsStore.getState().submit(EP, "flash", { disk: "/dev/sda" });
    expect(useOpsStore.getState().job).toMatchObject({ kind: "flash", status: "awaiting-confirm" });
    expect(useOpsStore.getState().confirmPending).toBe(true);
  });

  it("sets error on failure", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: false, status: 400 })));
    await useOpsStore.getState().submit(EP, "flash", {});
    expect(useOpsStore.getState().error).toBeTruthy();
  });
});

describe("confirm guard", () => {
  it("does NOT call /confirm if guardAcknowledged is false", async () => {
    useOpsStore.setState({ job: PREVIEW_JOB, confirmPending: true, guardAcknowledged: false });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await useOpsStore.getState().confirm(EP);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("calls /confirm when guardAcknowledged is true", async () => {
    useOpsStore.setState({ job: PREVIEW_JOB, confirmPending: true, guardAcknowledged: true });
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, json: () => Promise.resolve(DONE_JOB) }),
      ),
    );
    await useOpsStore.getState().confirm(EP);
    expect(useOpsStore.getState().job?.status).toBe("done");
    expect(useOpsStore.getState().confirmPending).toBe(false);
  });

  it("acknowledgeGuard sets guardAcknowledged", () => {
    useOpsStore.getState().acknowledgeGuard();
    expect(useOpsStore.getState().guardAcknowledged).toBe(true);
  });
});

describe("cancel", () => {
  it("posts to /api/ops/{id}/cancel", async () => {
    const cancelled: OpsJob = { ...PREVIEW_JOB, status: "cancelled" };
    useOpsStore.setState({ job: PREVIEW_JOB });
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, json: () => Promise.resolve(cancelled) }),
      ),
    );
    await useOpsStore.getState().cancel(EP);
    expect(useOpsStore.getState().job?.status).toBe("cancelled");
  });
});

describe("reset", () => {
  it("clears all state", () => {
    useOpsStore.setState({ job: PREVIEW_JOB, error: "prev", guardAcknowledged: true });
    useOpsStore.getState().reset();
    expect(useOpsStore.getState().job).toBeNull();
    expect(useOpsStore.getState().error).toBeNull();
    expect(useOpsStore.getState().guardAcknowledged).toBe(false);
  });
});
