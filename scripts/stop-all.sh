#!/bin/bash
# Stop all Docker containers for the project

set -e

cd "$(dirname "$0")/.."

echo "Stopping all containers..."
docker compose down

echo ""
echo "All containers stopped."
echo ""
echo "To also remove volumes (database data): docker compose down -v"
