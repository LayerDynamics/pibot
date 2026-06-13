/**
 * T12.5.6 — Native-notification wiring (SPEC-3 FR-22).
 *
 * `lib/notify.ts` holds the pure, focus-gated + debounced notifier; this store connects
 * it to the live telemetry alerts stream so OS notifications actually fire. Call `start()`
 * once at app startup (App.tsx): it subscribes to the telemetry store and raises a
 * notification for each new alert set. `enabled` lets the operator mute notifications
 * without tearing down the subscription.
 */
import { create } from "zustand";

import { notifyAlerts } from "../lib/notify";
import { useTelemetryStore } from "./telemetryStore";

interface NotifyState {
  /** When false, alerts are observed but no OS notification is raised. */
  enabled: boolean;
  setEnabled: (v: boolean) => void;
  /**
   * Subscribe the telemetry alerts stream to the OS notifier. Returns an unsubscribe
   * function (wire it into a React effect's cleanup). `notifyAlerts` itself enforces the
   * focus gate + per-message debounce, so this only forwards new alert sets.
   */
  start: () => () => void;
}

export const useNotifyStore = create<NotifyState>((set, get) => ({
  enabled: true,
  setEnabled: (v) => set({ enabled: v }),
  start: () =>
    useTelemetryStore.subscribe((state, prev) => {
      if (!get().enabled) return;
      // `computeAlerts` returns a fresh array per snapshot, so reference inequality
      // detects a new alert set; only forward when there is something to announce.
      if (state.alerts !== prev.alerts && state.alerts.length > 0) {
        notifyAlerts(state.alerts);
      }
    }),
}));
