import "@testing-library/jest-dom/vitest";

// jsdom does not implement ResizeObserver, but Radix UI primitives (e.g. Slider) call it
// on mount. Provide a no-op stub so components that render Radix widgets are testable.
// The real WKWebView ships ResizeObserver, so this only affects the test environment.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  } as unknown as typeof ResizeObserver;
}
