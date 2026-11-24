#!/usr/bin/env bash
# Start both Flask API and Django dashboard.
# Usage: ./start.sh
#
# If port 5000 is already in use by another app, Flask will start on port 5001 instead.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Activate virtual environment if it exists.
if [ -f "$SCRIPT_DIR/.env/bin/activate" ]; then
    echo "Activating virtual environment..."
    source "$SCRIPT_DIR/.env/bin/activate"
else
    echo "Warning: .env not found — using system Python."
fi

FLASK_PORT=5000
DJANGO_API_URL="http://127.0.0.1:5000/api"

# Check if our Flask API is already running (expects JSON health response).
HEALTH_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/health 2>/dev/null || echo "000")

if [ "$HEALTH_CHECK" = "200" ]; then
    echo "Flask API is already running on port 5000 — skipping."
else
    echo "Starting Flask API on port 5000..."
    PORT=5000 python app.py > /tmp/flask.log 2>&1 &

    for i in $(seq 1 10); do
        HC=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/health 2>/dev/null || echo "000")
        if [ "$HC" = "200" ]; then
            echo "Flask API is ready."
            break
        fi
        sleep 0.5
    done

    HC=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/health 2>/dev/null || echo "000")
    if [ "$HC" != "200" ]; then
        echo "Port 5000 unavailable — starting Flask on port 5001..."
        FLASK_PORT=5001
        DJANGO_API_URL="http://127.0.0.1:5001/api"

        pkill -f "python app.py" 2>/dev/null || true
        sleep 0.5

        PORT=5001 python app.py > /tmp/flask.log 2>&1 &

        for i in $(seq 1 10); do
            HC=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5001/api/health 2>/dev/null || echo "000")
            if [ "$HC" = "200" ]; then
                echo "Flask API is ready on port $FLASK_PORT."
                break
            fi
            sleep 0.5
        done

        HC=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5001/api/health 2>/dev/null || echo "000")
        if [ "$HC" != "200" ]; then
            echo "Error: Could not start Flask API on port $FLASK_PORT."
            exit 1
        fi
    fi
fi

echo "Applying Django migrations..."
DJANGO_FLASK_API_URL="$DJANGO_API_URL" python manage.py migrate --noinput 2>&1 | grep -v "^$" || true

echo "Starting Django dashboard on port 8000..."
DJANGO_FLASK_API_URL="$DJANGO_API_URL" python manage.py runserver 8000 &
DJANGO_PID=$!

# Kill Flask when Ctrl+C is pressed.
cleanup() {
    echo ""
    echo "Shutting down servers..."
    pkill -f "python app.py" 2>/dev/null || true
    kill "$DJANGO_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "Done."
}
trap cleanup INT TERM

echo ""
echo "Services running:"
echo "  Flask API   → http://127.0.0.1:$FLASK_PORT"
echo "  Django      → http://127.0.0.1:8000"
echo "Press Ctrl+C to stop."

# Keep script alive so Ctrl+C triggers cleanup.
wait "$DJANGO_PID" 2>/dev/null || true
cleanup
