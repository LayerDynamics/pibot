/**
 * Intentionally empty.
 *
 * The `@tauri-apps/plugin-notification` package is now a real dependency (see
 * app/package.json) and ships its own type declarations, so the earlier ambient
 * `declare module` shim is obsolete — keeping it would shadow the real types and hide
 * `isPermissionGranted` / `requestPermission`. In tests the module is aliased to the
 * in-repo mock via `vite.config.ts` (`test.alias`).
 */
export {};
