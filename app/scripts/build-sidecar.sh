#!/usr/bin/env bash
# Build the PiBot Mission Control sidecar (pibot.mc) into a standalone binary and place
# it where Tauri's externalBin expects it (SPEC-3 / M12.1 T12.1.7, resolves OQ-4 ->
# PyInstaller one-file). The [ml] extra is intentionally NOT bundled — the sidecar only
# talks to pibotd; jax/torch/openpi live on the robot.
#
# Usage: bash app/scripts/build-sidecar.sh
set -euo pipefail

cd "$(dirname "$0")/.."          # -> app/
APP_DIR="$PWD"
REPO="$(cd .. && pwd)"
VENV="${VENV:-$REPO/.venv/bin}"

# Tauri externalBin names binaries `<name>-<target-triple>`; compute the host triple.
TRIPLE="$("$VENV/python" - <<'PY'
import platform
mach = platform.machine().lower()
arch = "aarch64" if mach in ("arm64", "aarch64") else "x86_64"
print(f"{arch}-apple-darwin")
PY
)"

OUT_DIR="$APP_DIR/src-tauri/binaries"
BUILD_DIR="$REPO/build/sidecar"
mkdir -p "$OUT_DIR" "$BUILD_DIR"

echo "== building sidecar (pibot.mc) -> pibot-mc-host-$TRIPLE =="
"$VENV/python" -m PyInstaller \
  --noconfirm --clean --onefile \
  --name pibot-mc-host \
  --distpath "$BUILD_DIR/dist" \
  --workpath "$BUILD_DIR/work" \
  --specpath "$BUILD_DIR" \
  --collect-all aiohttp \
  "$REPO/pibot/mc/__main__.py"

install -m 0755 "$BUILD_DIR/dist/pibot-mc-host" "$OUT_DIR/pibot-mc-host-$TRIPLE"
echo "== wrote $OUT_DIR/pibot-mc-host-$TRIPLE =="
