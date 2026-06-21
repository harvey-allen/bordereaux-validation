#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Set environment to development for CI testing
export ENVIRONMENT="${ENVIRONMENT:-development}"

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

echo "==> Environment: $ENVIRONMENT"
echo "==> Backend: install dependencies"
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r backend/requirements.txt
"$PYTHON_BIN" -m pip install ruff

echo "==> Backend: ruff check"
ruff check backend

echo "==> Backend: unit tests"
(
  cd backend
  ENVIRONMENT="$ENVIRONMENT" "$PYTHON_BIN" -m pytest tests -q --cov-fail-under=75
)

echo "==> Frontend: install dependencies"
(
  cd frontend
  npm install
)

echo "==> Frontend: lint"
(
  cd frontend
  npm run lint
)

echo "==> Frontend: unit tests"
(
  cd frontend
  npm run test:coverage
)

echo "==> Coverage summary"
"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

root = Path.cwd()
backend = json.loads((root / "backend" / "coverage-backend.json").read_text())
frontend = json.loads((root / "frontend" / "coverage" / "coverage-summary.json").read_text())

backend_total = backend.get("totals", {}).get("percent_covered", 0.0)
front_totals = frontend.get("total", {}).get("lines", {})
frontend_total = front_totals.get("pct", 0.0)

backend_covered = backend.get("totals", {}).get("covered_lines", 0)
backend_lines = backend.get("totals", {}).get("num_statements", 0)
frontend_covered = front_totals.get("covered", 0)
frontend_lines = front_totals.get("total", 0)

overall_pct = 0.0
overall_lines = backend_lines + frontend_lines
if overall_lines:
    overall_pct = ((backend_covered + frontend_covered) / overall_lines) * 100

print(f"Backend coverage:  {backend_total:.2f}%")
print(f"Frontend coverage: {frontend_total:.2f}%")
print(f"Overall coverage:  {overall_pct:.2f}%")

if overall_pct < 75.0:
    raise SystemExit("Overall coverage gate failed (<75%).")
PY

echo "All CI checks passed"
