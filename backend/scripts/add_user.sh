#!/usr/bin/env bash
# Add or update a user subscription in PostgreSQL.
# Wraps add_user.py — resolves the venv automatically.
#
# Usage:
#   ./add_user.sh --email user@example.com [OPTIONS]
#
# Options (passed through to add_user.py):
#   --email              EMAIL   (required)
#   --excel-user-id      ID      Override generated Excel user ID
#   --display-name       NAME    Display name
#   --tier               TIER    trial | starter | professional | enterprise (default: trial)
#   --inactive                   Create/update user as inactive
#   --regenerate-api-key         Regenerate API key if user already exists

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
exec "$PYTHON" "$SCRIPT_DIR/add_user.py" "$@"
