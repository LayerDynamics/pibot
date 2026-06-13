import { useState } from "react";

import ConfirmModal from "../components/ConfirmModal";
import OpLog from "../components/OpLog";
import OpPreview from "../components/OpPreview";
import type { McEndpoint } from "../lib/api/types";
import { useOpsStore } from "../stores/opsStore";

type OpsKind = "flash" | "clone" | "restore" | "eeprom" | "firmware" | "deploy";

const OPS_KINDS: OpsKind[] = ["flash", "clone", "restore", "eeprom", "firmware", "deploy"];

interface Props {
  ep: McEndpoint | null;
}

export default function Provisioning({ ep }: Props) {
  const [kind, setKind] = useState<OpsKind>("deploy");
  const [argsText, setArgsText] = useState<string>("");

  const { job, confirmPending, guardAcknowledged, error, submit, acknowledgeGuard, confirm, cancel, reset } =
    useOpsStore();

  async function handleSubmit() {
    if (!ep) return;
    let parsedArgs: Record<string, string> = {};
    const trimmed = argsText.trim();
    if (trimmed) {
      try {
        parsedArgs = JSON.parse(trimmed) as Record<string, string>;
      } catch {
        // Invalid JSON — submit with no args; the dry-run preview surfaces the gap.
        parsedArgs = {};
      }
    }
    await submit(ep, kind, parsedArgs);
  }

  async function handleConfirm() {
    if (!ep) return;
    await confirm(ep);
  }

  async function handleCancel() {
    if (!ep) return;
    await cancel(ep);
    reset();
  }

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="provisioning-screen">
      {!ep && (
        <p className="text-xs text-zinc-500">Connect to a robot to use provisioning ops.</p>
      )}

      {error && (
        <p className="text-xs text-red-400" data-testid="ops-error">{error}</p>
      )}

      {/* Op selector */}
      <div className="flex flex-col gap-2">
        <label className="text-xs text-zinc-400">Operation</label>
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as OpsKind)}
          className="rounded bg-zinc-800 border border-zinc-700 px-2 py-1.5 text-sm text-white"
          data-testid="ops-kind-select"
        >
          {OPS_KINDS.map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
      </div>

      {/* Op arguments (e.g. the target device for flash) — passed through to the
          dry-run preview and, after confirm + wrong-disk guard, the real op. */}
      <div className="flex flex-col gap-2">
        <label className="text-xs text-zinc-400">Arguments (JSON)</label>
        <textarea
          value={argsText}
          onChange={(e) => setArgsText(e.target.value)}
          placeholder='{"device": "/dev/disk4"}'
          rows={2}
          className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 font-mono text-xs text-white"
          data-testid="ops-args"
        />
      </div>

      <button
        onClick={handleSubmit}
        disabled={!ep || !!job}
        className="rounded bg-zinc-700 px-4 py-2 text-sm text-white hover:bg-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed"
        data-testid="ops-submit"
      >
        Preview
      </button>

      {/* Preview + confirm flow */}
      {job && (
        <div className="flex flex-col gap-3">
          <OpPreview job={job} />

          {(job.status === "running" || job.status === "done" || job.status === "error") && (
            <OpLog lines={job.log} />
          )}

          {job.status === "done" && (
            <p className="text-xs text-green-400" data-testid="ops-done">Operation complete.</p>
          )}

          {job.status === "error" && (
            <p className="text-xs text-red-400" data-testid="ops-error-status">Operation failed.</p>
          )}

          {(job.status === "awaiting-confirm" || job.status === "preview") && (
            <div className="flex gap-2">
              <button
                onClick={handleCancel}
                className="rounded bg-zinc-700 px-3 py-1.5 text-xs text-white hover:bg-zinc-600"
                data-testid="ops-cancel"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      )}

      {/* Confirm modal */}
      {confirmPending && job && (
        <ConfirmModal
          job={job}
          guardAcknowledged={guardAcknowledged}
          onAcknowledgeGuard={acknowledgeGuard}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
        />
      )}
    </div>
  );
}
