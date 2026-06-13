/**
 * Regression guard for the Mission Control CSP (app/src-tauri/tauri.conf.json).
 *
 * The sidecar binds an OS-assigned port (`pibot.mc --port 0`) and the Rust core hands the
 * webview `http://127.0.0.1:{port}` (lib.rs `set_url`). A `connect-src` of bare
 * `http://127.0.0.1` matches ONLY port 80 in CSP semantics, so every sidecar HTTP/WS call
 * on the random port was blocked at runtime — and the Tauri notification plugin's IPC call
 * to `ipc://localhost/...` was blocked too. This test pins the *specific* directives that
 * were missing so the bare/no-port form can't regress back in. It is a guard, not proof:
 * actual enforcement is only verified by rebuilding the app and watching a clean console.
 */
import { describe, expect, it } from "vitest";

import tauriConfig from "../src-tauri/tauri.conf.json";

function connectSrcSources(): string[] {
  const directive = tauriConfig.app.security.csp
    .split(";")
    .map((d) => d.trim())
    .find((d) => d.startsWith("connect-src "));
  if (!directive) {
    throw new Error("CSP has no connect-src directive");
  }
  return directive.slice("connect-src ".length).trim().split(/\s+/);
}

describe("Mission Control CSP connect-src", () => {
  it("allows the sidecar on any loopback port (not just :80)", () => {
    const sources = connectSrcSources();
    expect(sources).toContain("http://127.0.0.1:*");
    expect(sources).toContain("ws://127.0.0.1:*");
  });

  it("never regresses to the bare, port-80-only loopback form", () => {
    const sources = connectSrcSources();
    expect(sources).not.toContain("http://127.0.0.1");
    expect(sources).not.toContain("ws://127.0.0.1");
  });

  it("allows the Tauri notification plugin IPC channel", () => {
    const sources = connectSrcSources();
    expect(sources).toContain("ipc:");
    expect(sources).toContain("http://ipc.localhost");
  });
});
