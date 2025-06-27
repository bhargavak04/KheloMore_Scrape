#!/bin/bash
set -e

# Print environment for debugging
echo "=== Starting Application ==="

# Set environment variables
export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
export PYTHONUNBUFFERED=1

# Install dependencies
pip install -r requirements.txt
python -m playwright install --with-deps

# Create data directory
mkdir -p data

# Set default port if not provided
export PORT=${PORT:-8080}

# Start the application
echo "Starting Gunicorn on port $PORT"
exec gunicorn --bind 0.0.0.0:$PORT \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --worker-class=gthread \
    --log-level=debug \
    --access-logfile - \
    --error-logfile - \
    app:app
