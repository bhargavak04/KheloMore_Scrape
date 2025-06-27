#!/bin/bash
set -e

# Set environment variables
export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright and browsers
python -m playwright install --with-deps
python -m playwright install-deps

# Make sure the data directory exists
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
