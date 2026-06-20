#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

echo "==> Backend: install dependencies"
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r backend/requirements.txt
"$PYTHON_BIN" -m pip install ruff

echo "==> Backend: ruff check"
ruff check backend

echo "==> Backend: unit tests"
(
  cd backend
  "$PYTHON_BIN" -m pytest tests -q
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
  npm test
)

echo "All CI checks passed"
