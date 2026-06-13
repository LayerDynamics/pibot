/**
 * Ambient declaration for the Tauri notification plugin.
 *
 * The module is provided at build/test time via the `@tauri-apps/plugin-notification`
 * alias in `vite.config.ts` (the in-repo mock), so the package is not in `node_modules`
 * and `tsc` cannot resolve the dynamic import in `lib/notify.ts` on its own. This
 * ambient declaration gives `tsc` the type without installing the package.
 *
 * NOTE: real OS-notification delivery still requires installing the actual
 * `@tauri-apps/plugin-notification` package + the Rust `tauri-plugin-notification`
 * (registered in `src-tauri/src/lib.rs` with a capability grant) and scoping the vite
 * alias to the test environment only — until then the alias routes to a no-op mock in
 * every build. Tracked in Todo.md (T12.5.6 / FR-22 delivery).
 */
declare module "@tauri-apps/plugin-notification" {
  export function sendNotification(options: { title: string; body: string }): void;
}
