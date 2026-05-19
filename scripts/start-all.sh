#!/bin/bash
# Start all services for development
# Supports both Docker mode and local dev mode

set -e

cd "$(dirname "$0")/.."

# Check for --docker flag
USE_DOCKER=false
if [ "$1" = "--docker" ]; then
    USE_DOCKER=true
fi

# Check for SSL certificates
CERT_DIR="$HOME/.office-addin-dev-certs"
if [ ! -f "$CERT_DIR/localhost.crt" ] || [ ! -f "$CERT_DIR/localhost.key" ]; then
    echo "Error: SSL certificates not found at $CERT_DIR"
    echo "Run: npx office-addin-dev-certs install"
    exit 1
fi

if [ "$USE_DOCKER" = true ]; then
    # Docker mode
    if ! docker info > /dev/null 2>&1; then
        echo "Error: Docker is not running. Please start Docker Desktop."
        exit 1
    fi

    # Copy SSL certificates to nginx/certs
    echo "Copying SSL certificates..."
    mkdir -p nginx/certs
    cp "$CERT_DIR/localhost.crt" nginx/certs/
    cp "$CERT_DIR/localhost.key" nginx/certs/

    # Use Docker-specific config for frontend
    echo "Using Docker config..."
    cp frontend/config.docker.js frontend/config.js

    # Create .env file if it doesn't exist
    if [ ! -f .env ]; then
        echo "Creating .env file from .env.example..."
        cp .env.example .env
    fi

    # Cleanup function to restore config
    cleanup_docker() {
        echo ""
        echo "Restoring local config..."
        git checkout frontend/config.js 2>/dev/null || true
        echo "Stopping containers..."
        docker compose down
        echo "Done"
    }
    trap cleanup_docker SIGINT SIGTERM

    echo ""
    echo "========================================="
    echo "  Starting Docker containers..."
    echo "========================================="
    echo ""

    docker compose up --build -d

    echo ""
    echo "========================================="
    echo "  Docker Development Mode"
    echo "========================================="
    echo "  Frontend: https://localhost (via nginx)"
    echo "  Backend:  https://localhost/api/ (via nginx)"
    echo "  Direct Backend: http://localhost:8000"
    echo "  Direct Frontend: http://localhost:3000"
    echo "  Database: postgresql://postgres:postgres@localhost:5432/bordereaux"
    echo ""
    echo "  Hot-reload: Backend code changes auto-reload"
    echo "  Live files: Frontend files are mounted"
    echo "========================================="
    echo ""
    echo "Press Ctrl+C to stop and restore local config"
    echo ""

    docker compose logs -f
else
    # Local dev mode (no Docker)
    echo ""
    echo "========================================="
    echo "  Starting in Local Development Mode"
    echo "========================================="
    echo ""

    # Kill existing processes on ports
    echo "Clearing ports..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    sleep 1

    # Ensure PostgreSQL is running (via Homebrew)
    echo "Checking PostgreSQL..."
    if ! brew services list | grep -q "postgresql.*started"; then
        echo "Starting PostgreSQL..."
        brew services start postgresql@18 2>/dev/null || brew services start postgresql 2>/dev/null || true
        sleep 2
    fi
    echo "✓ PostgreSQL running"

    # Start backend
    echo "Starting backend..."
    cd backend
    if [ ! -d ".venv" ]; then
        echo "Creating Python virtual environment..."
        python3 -m venv .venv
        source .venv/bin/activate
        pip install -r requirements.txt
    else
        source .venv/bin/activate
    fi

    python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 \
        --ssl-keyfile "$CERT_DIR/localhost.key" \
        --ssl-certfile "$CERT_DIR/localhost.crt" &
    BACKEND_PID=$!
    cd ..

    # Wait for backend to start
    echo "Waiting for backend..."
    sleep 3

    # Verify backend is running
    if curl -sk https://127.0.0.1:8000/health > /dev/null 2>&1; then
        echo "✓ Backend running at https://127.0.0.1:8000"
    else
        echo "⚠ Backend may still be starting..."
    fi

    # Start frontend
    echo "Starting frontend..."
    cd frontend
    npx http-server . -p 3000 -c-1 -S \
        -C "$CERT_DIR/localhost.crt" \
        -K "$CERT_DIR/localhost.key" &
    FRONTEND_PID=$!
    cd ..

    sleep 2
    echo "✓ Frontend running at https://localhost:3000"

    echo ""
    echo "========================================="
    echo "  All Services Running (HTTPS)"
    echo "========================================="
    echo "  Backend:  https://127.0.0.1:8000"
    echo "  Frontend: https://localhost:3000"
    echo "  Database: postgresql://harveyallen@localhost:5432/bordereaux"
    echo "========================================="
    echo ""
    echo "Press Ctrl+C to stop all servers"
    echo ""

    # Cleanup on exit
    trap "echo 'Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Done'; exit 0" SIGINT SIGTERM

    # Wait for processes
    wait
fi
