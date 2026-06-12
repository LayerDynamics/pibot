#!/usr/bin/env bash
# Run every quality gate for the PiBot Control Suite. Non-zero exit on any failure.
# This is the per-task and per-milestone definition of done (see docs/plans/).
set -euo pipefail

cd "$(dirname "$0")/.."

VENV="${VENV:-.venv/bin}"
RUFF="$VENV/ruff"
MYPY="$VENV/mypy"
PYTEST="$VENV/pytest"

# Type-check the suite's source packages. `agent/` is added from milestone M4.
MYPY_TARGETS=("pibot")
[ -d agent ] && MYPY_TARGETS+=("agent")

echo "== ruff check =="
"$RUFF" check .

echo "== ruff format --check =="
"$RUFF" format --check .

echo "== mypy =="
"$MYPY" "${MYPY_TARGETS[@]}"

echo "== pytest (with coverage gate) =="
"$PYTEST" --cov=pibot --cov=agent --cov-report=term-missing

# Desktop app gate (PiBot Mission Control — SPEC-3 / M12). Runs when the JS/Rust
# toolchain is present so Python-only contributors aren't blocked; CI runs it on macOS.
if [ -d app ] && command -v pnpm >/dev/null 2>&1; then
  echo "== desktop app: frontend lint + typecheck + test =="
  ( cd app && pnpm install --frozen-lockfile --prefer-offline >/dev/null 2>&1 \
      && pnpm lint && pnpm typecheck && pnpm test )
  if command -v cargo >/dev/null 2>&1; then
    echo "== desktop app: cargo fmt + clippy + test =="
    ( cd app/src-tauri && cargo fmt --check \
        && cargo clippy --all-targets -- -D warnings && cargo test )
  else
    echo "== desktop app: cargo gate skipped (no cargo) =="
  fi
else
  echo "== desktop app gate skipped (no app/ or pnpm) =="
fi

echo ""
echo "ALL GATES PASSED"
