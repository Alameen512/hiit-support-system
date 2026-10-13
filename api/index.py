"""Vercel serverless entry point.

Vercel's Python runtime looks for a WSGI callable named `app` in this file.
vercel.json rewrites every URL to this function, and WhiteNoise (see
config/settings.py) serves CSS/JS from the same function.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()
application = app
