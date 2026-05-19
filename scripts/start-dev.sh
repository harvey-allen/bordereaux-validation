#!/bin/bash
# Start services in development mode (without Docker)
# Useful for faster iteration during development

set -e

cd "$(dirname "$0")/.."

echo "Starting in development mode (no Docker)..."
echo ""

# Kill existing processes
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
sleep 1

# Check for SSL certificates
CERT_DIR="$HOME/.office-addin-dev-certs"
if [ ! -f "$CERT_DIR/localhost.crt" ] || [ ! -f "$CERT_DIR/localhost.key" ]; then
    echo "Error: SSL certificates not found at $CERT_DIR"
    echo "Run: npx office-addin-dev-certs install"
    exit 1
fi

# Start backend in background
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
sleep 2

# Start frontend in background
echo "Starting frontend..."
cd frontend
npx http-server . -p 3000 -c-1 -S \
  -C "$CERT_DIR/localhost.crt" \
  -K "$CERT_DIR/localhost.key" &
FRONTEND_PID=$!
cd ..

echo ""
echo "========================================="
echo "  Development Mode (HTTPS)"
echo "  Backend:  https://127.0.0.1:8000"
echo "  Frontend: https://localhost:3000"
echo "========================================="
echo ""
echo "Press Ctrl+C to stop all servers"

# Wait for Ctrl+C and cleanup
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Servers stopped'; exit 0" SIGINT SIGTERM
wait
