#!/bin/bash
# Start only the Frontend service using Docker

set -e

cd "$(dirname "$0")/.."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

echo "Starting frontend container..."
docker compose up --build -d frontend

echo ""
echo "========================================="
echo "  Frontend: http://localhost:3000"
echo "========================================="
echo ""
echo "View logs: docker compose logs -f frontend"
echo ""

docker compose logs -f frontend
