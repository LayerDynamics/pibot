/**
 * T12.5.6 — Native OS notification helper (Tauri sendNotification).
 *
 * Rules:
 *  - Only fires when the window is unfocused (document.hasFocus() === false).
 *  - Debounced: once a message fires, the same message is suppressed for DEBOUNCE_MS.
 *  - Driven by the alerts string array from alerts.ts — no new threshold logic.
 */

export const DEBOUNCE_MS = 30_000;

let _sendFn: (title: string, body: string) => void = _tauriSend;
const _lastFired: Map<string, number> = new Map();

/** Overridable in tests. */
export function setSendFn(fn: (title: string, body: string) => void): void {
  _sendFn = fn;
}

export function resetSendFn(): void {
  _sendFn = _tauriSend;
}

export function clearDebounce(): void {
  _lastFired.clear();
}

/**
 * Fire OS notifications for any new alert strings, subject to focus + debounce rules.
 */
export function notifyAlerts(alertStrings: string[]): void {
  if (document.hasFocus()) return;

  const now = Date.now();
  for (const msg of alertStrings) {
    const last = _lastFired.get(msg) ?? 0;
    if (now - last < DEBOUNCE_MS) continue;
    _lastFired.set(msg, now);
    _sendFn("PiBot Alert", msg);
  }
}

function _tauriSend(title: string, body: string): void {
  // Tauri v2 notification plugin — only available in the app bundle. Request the OS
  // notification permission on first use, then deliver.
  /* @vite-ignore */
  import("@tauri-apps/plugin-notification")
    .then(async ({ isPermissionGranted, requestPermission, sendNotification }) => {
      let granted = await isPermissionGranted();
      if (!granted) {
        granted = (await requestPermission()) === "granted";
      }
      if (granted) {
        sendNotification({ title, body });
      }
    })
    .catch(() => {
      /* not in a Tauri context (browser preview / tests) — silently skip */
    });
}
