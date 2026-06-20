#!/usr/bin/env bash
#
# User management CLI wrapper
#
# Usage:
#   ./manage_users.sh list [--org-id <id>] [--tier <tier>] [--active] [--inactive]
#   ./manage_users.sh get --id <id> | --email <email> | --excel-user-id <id>
#   ./manage_users.sh create --email <email> --org-id <org_id> [--display-name <name>] [--tier <tier>]
#   ./manage_users.sh update --id <id> [--email <email>] [--display-name <name>] [--org-id <id>] [--tier <tier>] [--active true|false]
#   ./manage_users.sh delete --id <id> [--force]
#   ./manage_users.sh activate --id <id>
#   ./manage_users.sh deactivate --id <id>
#   ./manage_users.sh regenerate-key --id <id>
#
# Examples:
#   ./manage_users.sh list
#   ./manage_users.sh list --org-id 1 --active
#   ./manage_users.sh get --email "user@example.com"
#   ./manage_users.sh create --email "new@example.com" --org-id 1 --tier bordereaux
#   ./manage_users.sh update --id 1 --tier developer
#   ./manage_users.sh deactivate --id 1
#   ./manage_users.sh regenerate-key --id 1
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

# Run the admin script with 'user' subcommand
exec "$PYTHON_BIN" "$SCRIPT_DIR/db_admin.py" user "$@"
