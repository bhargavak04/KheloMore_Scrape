web: chmod +x start.sh && ./start.sh
# Alternative if the above doesn't work:
# web: gunicorn --bind 0.0.0.0:$PORT --workers 4 --threads 4 --timeout 120 --worker-class=gthread --log-level=debug --access-logfile - --error-logfile - wsgi:application
