#!/usr/bin/env bash
# Clear data from PostgreSQL tables (keeps schema).
# Wraps clear_database.py — resolves the venv automatically.
#
# Usage:
#   ./clear_database.sh [OPTIONS]
#
# Options:
#   --table  TABLE   Target a specific table instead of all tables.
#                    Can be specified multiple times.
#   --yes            Skip confirmation prompt.
#
# Examples:
#   ./clear_database.sh --yes                          # clear everything
#   ./clear_database.sh --table validation_runs        # clear one table
#   ./clear_database.sh --table validation_runs --table test_results --yes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

PYTHON=""
if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  PYTHON="$BACKEND_DIR/.venv/bin/python"
elif [[ -x "$(dirname "$BACKEND_DIR")/.venv/bin/python" ]]; then
  PYTHON="$(dirname "$BACKEND_DIR")/.venv/bin/python"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
else
  echo "Error: could not find a Python interpreter. Activate a venv or install python3." >&2
  exit 1
fi

cd "$BACKEND_DIR"
export PYTHONPATH="$BACKEND_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" "$SCRIPT_DIR/clear_database.py" "$@"
