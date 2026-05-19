#!/bin/bash
# Start only the Backend service using Docker

set -e

cd "$(dirname "$0")/.."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker Desktop."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from .env.example..."
    cp .env.example .env
fi

echo "Starting backend and database containers..."
docker compose up --build -d db backend

echo ""
echo "========================================="
echo "  Backend: http://localhost:8000"
echo "  Health:  http://localhost:8000/health"
echo "========================================="
echo ""
echo "View logs: docker compose logs -f backend"
echo ""

docker compose logs -f backend
