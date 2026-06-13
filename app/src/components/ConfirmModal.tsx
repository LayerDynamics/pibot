import * as AlertDialog from "@radix-ui/react-alert-dialog";

import type { OpsJob } from "../stores/opsStore";

const DESTRUCTIVE = new Set(["flash", "clone", "restore", "eeprom"]);

interface Props {
  job: OpsJob;
  guardAcknowledged: boolean;
  onAcknowledgeGuard: () => void;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmModal({
  job,
  guardAcknowledged,
  onAcknowledgeGuard,
  onConfirm,
  onCancel,
}: Props) {
  const isDestructive = DESTRUCTIVE.has(job.kind);
  const canConfirm = !isDestructive || guardAcknowledged;

  return (
    <AlertDialog.Root open>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 bg-black/60" />
        <AlertDialog.Content
          data-testid="confirm-modal"
          className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-96 rounded-lg bg-zinc-900 border border-zinc-700 p-6 flex flex-col gap-4 shadow-xl"
        >
          <AlertDialog.Title className="text-base font-semibold text-white">
            {isDestructive ? "⚠ Destructive operation" : "Confirm operation"}
          </AlertDialog.Title>

          <AlertDialog.Description className="text-sm text-zinc-400">
            {isDestructive
              ? `${job.kind.toUpperCase()} will irreversibly overwrite the target. Review the dry-run output above before proceeding.`
              : `This will run ${job.kind}. Review the preview above.`}
          </AlertDialog.Description>

          {isDestructive && (
            <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
              <input
                type="checkbox"
                data-testid="guard-checkbox"
                checked={guardAcknowledged}
                onChange={onAcknowledgeGuard}
                className="accent-red-500"
              />
              I have verified the target disk/device and understand the risk.
            </label>
          )}

          <div className="flex gap-3 justify-end">
            <AlertDialog.Cancel asChild>
              <button
                data-testid="modal-cancel"
                onClick={onCancel}
                className="rounded bg-zinc-700 px-4 py-2 text-sm text-white hover:bg-zinc-600"
              >
                Cancel
              </button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <button
                data-testid="modal-confirm"
                onClick={onConfirm}
                disabled={!canConfirm}
                className="rounded bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Confirm
              </button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
