/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Tauri expects a fixed dev port; `clearScreen: false` keeps Rust logs visible.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/vitest.setup.ts"],
    css: true,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // In tests (jsdom, no Tauri runtime) stub the native notification plugin. The
    // production build resolves the real `@tauri-apps/plugin-notification` package.
    alias: {
      "@tauri-apps/plugin-notification": new URL(
        "./src/__mocks__/tauri-plugin-notification.ts",
        import.meta.url,
      ).pathname,
    },
  },
});
