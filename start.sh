#!/usr/bin/env bash
# Start both Flask API (port 5000) and Django dashboard (port 8000).
# Usage: ./start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.env/bin/python"

# Use virtual environment Python if available, otherwise fall back to system python.
if [ -x "$VENV_PYTHON" ]; then
    PYTHON="$VENV_PYTHON"
else
    PYTHON="python"
fi

echo "Starting Flask API on port 5000..."
"$PYTHON" app.py > /tmp/flask.log 2>&1 &
FLASK_PID=$!

# Wait for Flask to be ready.
for i in $(seq 1 10); do
    if curl -s http://127.0.0.1:5000/api/health >/dev/null 2>&1; then
        echo "Flask API is ready."
        break
    fi
    sleep 0.5
done

echo "Starting Django dashboard on port 8000..."
"$PYTHON" manage.py runserver 8000 &
DJANGO_PID=$!

# Trap SIGINT to kill both processes when Ctrl+C is pressed.
cleanup() {
    echo ""
    echo "Shutting down servers..."
    kill "$FLASK_PID" "$DJANGO_PID" 2>/dev/null
    wait 2>/dev/null
    echo "Done."
    exit 0
}
trap cleanup INT TERM

echo ""
echo "Both services running:"
echo "  Flask API   → http://127.0.0.1:5000"
echo "  Django      → http://127.0.0.1:8000"
echo "Press Ctrl+C to stop."

# Wait for both processes; if either exits, clean up and exit.
wait "$FLASK_PID" "$DJANGO_PID" 2>/dev/null || true
cleanup
