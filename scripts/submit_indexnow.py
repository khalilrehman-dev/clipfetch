from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

HOST = "snipivo.online"
KEY = "af05b46d902c4d2eb185fb825f8c22d6"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITEMAP_PATH = PROJECT_ROOT / "app" / "static" / "sitemap.xml"


def read_sitemap_urls() -> list[str]:
    root = ET.parse(SITEMAP_PATH).getroot()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls: list[str] = []
    for node in root.findall("sm:url/sm:loc", ns):
        if not node.text:
            continue
        url = node.text.strip()
        if urlparse(url).hostname != HOST:
            raise SystemExit(f"Refusing URL outside {HOST}: {url}")
        urls.append(url)
    if not urls:
        raise SystemExit("No URLs found in sitemap.xml")
    return urls


def verify_remote_key() -> None:
    try:
        with urllib.request.urlopen(KEY_LOCATION, timeout=20) as response:
            body = response.read().decode("utf-8").strip()
    except Exception as exc:
        raise SystemExit(
            f"Could not verify the public IndexNow key file at {KEY_LOCATION}: {exc}\n"
            "Deploy the update first, then try again."
        ) from exc

    if body != KEY:
        raise SystemExit(
            f"IndexNow key file is reachable but its contents do not match the expected key.\n"
            f"Expected: {KEY}\n"
            f"Received: {body!r}"
        )

    print(f"Verified public IndexNow key file: {KEY_LOCATION}")


def submit_urls(urls: list[str]) -> None:
    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls,
    }
    request = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace").strip()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise SystemExit(f"IndexNow submission failed: HTTP {exc.code} {detail}") from exc
    except Exception as exc:
        raise SystemExit(f"IndexNow submission failed: {exc}") from exc

    print(f"IndexNow response: HTTP {status}")
    if body:
        print(body)
    if status not in (200, 202):
        raise SystemExit("IndexNow did not return a success response.")
    print(f"Submitted {len(urls)} URL(s) to IndexNow.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Snipivo's IndexNow key and submit changed URLs."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all-sitemap",
        action="store_true",
        help="Submit every URL currently listed in app/static/sitemap.xml.",
    )
    group.add_argument(
        "--url",
        action="append",
        help="Submit one changed Snipivo URL. Repeat --url to submit multiple URLs.",
    )
    parser.add_argument(
        "--skip-key-check",
        action="store_true",
        help="Skip the public key-file verification step.",
    )
    args = parser.parse_args()

    if args.all_sitemap:
        urls = read_sitemap_urls()
    else:
        urls = [item.strip() for item in (args.url or []) if item and item.strip()]
        if not urls:
            parser.error("At least one non-empty --url is required.")
        for url in urls:
            if urlparse(url).hostname != HOST:
                raise SystemExit(f"Refusing URL outside {HOST}: {url}")

    if not args.skip_key_check:
        verify_remote_key()

    print("URLs to submit:")
    for url in urls:
        print(f"  - {url}")

    submit_urls(urls)
    return 0


if __name__ == "__main__":
    sys.exit(main())
