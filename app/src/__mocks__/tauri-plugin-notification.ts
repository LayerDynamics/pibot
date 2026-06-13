/** Stub for @tauri-apps/plugin-notification — used in the test environment only. */
export function sendNotification(_opts: { title: string; body: string }): void {
  /* no-op in test context */
}

export async function isPermissionGranted(): Promise<boolean> {
  return true;
}

export async function requestPermission(): Promise<"granted" | "denied" | "default"> {
  return "granted";
}
