/**
 * @host-marked — requires built .app + hardware stand (see README.md)
 *
 * Flow: Flash dry-run → modal → guard checkbox required
 * Assertions: Confirm button disabled without guard check; enabled after check
 */
export const meta = {
  flow: "provisioning",
  status: "host-marked",
  reason: "Requires macOS GUI session + built Tauri .app + pibotd stand",
};

/*
Manual steps:
  1. Connect to "testbot"
  2. Navigate to Provisioning tab
  3. Select "flash" from the operation dropdown
  4. Click "Preview"
  Expected: Preview panel shows dry-run output; "Confirm" button appears disabled
  5. Do NOT check the guard checkbox; click "Confirm"
  Expected: Nothing happens — button remains disabled
  6. Check the guard checkbox ("I understand this is destructive")
  Expected: "Confirm" button becomes enabled
  7. Click "Confirm"
  Expected: Operation transitions to "running" → "done"; log panel shows output lines
*/
