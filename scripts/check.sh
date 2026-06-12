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

echo ""
echo "ALL GATES PASSED"
