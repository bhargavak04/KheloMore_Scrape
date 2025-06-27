#!/usr/bin/env bash
set -e

# Enable debugging
set -x

# Print environment for debugging
env

# Make sure we're in the right directory
cd "$(dirname "$0")"
pwd
ls -la

# Set environment variables
export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
export PYTHONUNBUFFERED=1

# Install Python dependencies if needed
if [ -f "requirements.txt" ]; then
    echo "Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# Install Playwright browsers if not already installed
if ! command -v playwright &> /dev/null; then
    echo "Installing Playwright..."
    python -m pip install --upgrade pip
    python -m pip install playwright
    python -m playwright install --with-deps
    python -m playwright install-deps
fi

# Create data directory if it doesn't exist
mkdir -p data

# Check if PORT is set
if [ -z "$PORT" ]; then
    echo "WARNING: PORT environment variable not set, defaulting to 8080"
    export PORT=8080
fi

# Print final environment
echo "Final environment:"
env

# Start the Flask app with Gunicorn
echo "Starting Gunicorn on port $PORT"
exec gunicorn --bind 0.0.0.0:$PORT \
    --workers 4 \
    --threads 4 \
    --timeout 120 \
    --worker-class=gthread \
    --log-level=debug \
    --access-logfile - \
    --error-logfile - \
    --preload \
    --log-file=- \
    --capture-output \
    --enable-stdio-inheritance \
    app:app
