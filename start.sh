#!/usr/bin/env bash
# Start both Flask API and Django dashboard.
# Usage: ./start.sh
#
# If port 5000 is already in use, Flask will start on port 5001 instead.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.env/bin/python"

# Use virtual environment Python if available, otherwise fall back to system python.
if [ -x "$VENV_PYTHON" ]; then
    PYTHON="$VENV_PYTHON"
else
    PYTHON="python"
fi

# ---------------------------------------------------------------------------
# 1. Detect port availability and configure Flask + Django accordingly.
# ---------------------------------------------------------------------------
FLASK_PORT=5000
DJANGO_API_URL="http://127.0.0.1:5000/api"

if ! curl -s http://127.0.0.1:5000/api/health >/dev/null 2>&1; then
    # Port 5000 is free — try to start Flask there.
    echo "Starting Flask API on port 5000..."
    PORT=5000 "$PYTHON" app.py > /tmp/flask.log 2>&1 &

    # Wait for Flask to be ready.
    for i in $(seq 1 10); do
        if curl -s http://127.0.0.1:5000/api/health >/dev/null 2>&1; then
            echo "Flask API is ready."
            break
        fi
        sleep 0.5
    done

    # If Flask failed to start on port 5000, fall back to 5001.
    if ! curl -s http://127.0.0.1:5000/api/health >/dev/null 2>&1; then
        echo "Port 5000 unavailable — starting Flask on port 5001..."
        FLASK_PORT=5001
        DJANGO_API_URL="http://127.0.0.1:5001/api"

        # Kill the failed process if still running.
        kill $(lsof -ti:5000) 2>/dev/null || true
        sleep 0.5

        PORT=5001 "$PYTHON" app.py > /tmp/flask.log 2>&1 &

        for i in $(seq 1 10); do
            if curl -s http://127.0.0.1:5001/api/health >/dev/null 2>&1; then
                echo "Flask API is ready on port $FLASK_PORT."
                break
            fi
            sleep 0.5
        done

        if ! curl -s http://127.0.0.1:5001/api/health >/dev/null 2>&1; then
            echo "Error: Could not start Flask API on port $FLASK_PORT."
            exit 1
        fi
    fi
else
    echo "Flask API is already running on port 5000 — skipping."
fi

# ---------------------------------------------------------------------------
# 2. Apply Django migrations before starting the server.
# ---------------------------------------------------------------------------
echo "Applying Django migrations..."
DJANGO_FLASK_API_URL="$DJANGO_API_URL" "$PYTHON" manage.py migrate --noinput 2>&1 | grep -v "^$" || true

# ---------------------------------------------------------------------------
# 3. Start Django dashboard (port 8000).
# ---------------------------------------------------------------------------
echo "Starting Django dashboard on port 8000..."
DJANGO_FLASK_API_URL="$DJANGO_API_URL" "$PYTHON" manage.py runserver 8000 &
DJANGO_PID=$!

# ---------------------------------------------------------------------------
# 4. Trap SIGINT to kill both processes when Ctrl+C is pressed.
# ---------------------------------------------------------------------------
cleanup() {
    echo ""
    echo "Shutting down servers..."
    pkill -f "python app.py" 2>/dev/null || true
    kill "$DJANGO_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "Done."
    exit 0
}
trap cleanup INT TERM

echo ""
echo "Services running:"
echo "  Flask API   → http://127.0.0.1:$FLASK_PORT"
echo "  Django      → http://127.0.0.1:8000"
echo "Press Ctrl+C to stop."

# Wait for both processes; if either exits, clean up and exit.
wait "$DJANGO_PID" 2>/dev/null || true
cleanup
