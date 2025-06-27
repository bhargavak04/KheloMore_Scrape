#!/bin/bash

# Install Playwright browsers
playwright install chromium

# Start the application
gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 app:app
