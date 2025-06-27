#!/usr/bin/env bash
set -e

# Make sure we're in the right directory
cd "$(dirname "$0")"

# Set environment variables
export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install Python dependencies if needed
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

# Install Playwright browsers if not already installed
if ! command -v playwright &> /dev/null; then
    python -m playwright install --with-deps
    python -m playwright install-deps
fi

# Create data directory if it doesn't exist
mkdir -p data

# Start the Flask app with Gunicorn
exec gunicorn --bind 0.0.0.0:$PORT \
    --workers 4 \
    --threads 4 \
    --timeout 120 \
    --worker-class=gthread \
    --log-level=info \
    --access-logfile - \
    --error-logfile - \
    --preload \
    app:app
