""
WSGI config for KheloMore Scraper.

This module contains the WSGI application used by Django's development server
and any production WSGI deployments.
"""

import os
from app import app as application  # noqa

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    application.run(host='0.0.0.0', port=port, debug=False)
