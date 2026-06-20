#!/usr/bin/env bash
#
# Organisation management CLI wrapper
#
# Usage:
#   ./manage_orgs.sh list [--filter <name>]
#   ./manage_orgs.sh get --id <id> | --name <name>
#   ./manage_orgs.sh create --name <name>
#   ./manage_orgs.sh update --id <id> --name <new_name>
#   ./manage_orgs.sh delete --id <id> [--force]
#
# Examples:
#   ./manage_orgs.sh list
#   ./manage_orgs.sh list --filter "Acme"
#   ./manage_orgs.sh get --name "Acme Corp"
#   ./manage_orgs.sh create --name "New Organisation"
#   ./manage_orgs.sh update --id 1 --name "Updated Name"
#   ./manage_orgs.sh delete --id 1 --force
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Activate virtual environment if present
if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
    source "$ROOT_DIR/.venv/bin/activate"
elif [[ -f "$ROOT_DIR/backend/.venv/bin/activate" ]]; then
    source "$ROOT_DIR/backend/.venv/bin/activate"
fi

# Determine Python binary
PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

# Run the admin script with 'org' subcommand
exec "$PYTHON_BIN" "$SCRIPT_DIR/db_admin.py" org "$@"
