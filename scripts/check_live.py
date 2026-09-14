"""Optional live smoke test.

Usage:
  python scripts/check_live.py 'https://www.tiktok.com/@creator/video/123...'
"""
import json
import os
import sys

from app.downloader import extract_metadata
from app.security import validate_tiktok_url

if len(sys.argv) != 2:
    raise SystemExit("Usage: python scripts/check_live.py '<public-tiktok-url>'")

url = validate_tiktok_url(sys.argv[1])
print(json.dumps(extract_metadata(url, int(os.getenv("MAX_DURATION_SECONDS", "1200"))), indent=2))
