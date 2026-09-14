from __future__ import annotations

from urllib.parse import urlparse


ALLOWED_TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "tiktokv.com",
    "www.tiktokv.com",
}


def validate_tiktok_url(raw_url: str) -> str:
    """Validate and normalize a user-supplied TikTok URL.

    Only HTTP(S) URLs on TikTok-owned hostnames are accepted. This is an
    important SSRF guard because the backend performs server-side network I/O.
    """
    url = (raw_url or "").strip()
    if not url:
        raise ValueError("Paste a TikTok video URL.")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// or https:// TikTok links are supported.")

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("Invalid TikTok URL.")

    # Keep the allow-list intentionally narrow. TikTok short links and the
    # common share host are covered without permitting arbitrary domains.
    if host not in ALLOWED_TIKTOK_HOSTS and not host.endswith(".tiktok.com"):
        raise ValueError("That link is not a supported TikTok URL.")

    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not allowed.")

    return url
