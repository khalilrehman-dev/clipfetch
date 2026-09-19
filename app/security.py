from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

Platform = Literal["tiktok", "instagram"]


ALLOWED_TIKTOK_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "tiktokv.com",
    "www.tiktokv.com",
}

ALLOWED_INSTAGRAM_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
    "instagr.am",
    "www.instagr.am",
}

INSTAGRAM_VIDEO_PREFIXES = ("/reel/", "/reels/", "/p/", "/tv/", "/share/reel/", "/share/p/")


def _basic_url_checks(raw_url: str) -> tuple[str, str, str]:
    url = (raw_url or "").strip()
    if not url:
        raise ValueError("Paste a TikTok or Instagram post URL.")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// or https:// TikTok and Instagram links are supported.")

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("Invalid media URL.")

    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not allowed.")

    return url, host, parsed.path or "/"


def validate_tiktok_url(raw_url: str) -> str:
    """Validate and normalize a user-supplied TikTok URL.

    The allow-list is intentionally narrow because Snipivo performs server-side
    network requests and should never become a general-purpose URL fetcher.
    """
    url, host, _path = _basic_url_checks(raw_url)

    if host not in ALLOWED_TIKTOK_HOSTS and not host.endswith(".tiktok.com"):
        raise ValueError("That link is not a supported TikTok URL.")

    return url


def validate_instagram_url(raw_url: str) -> str:
    """Validate a public Instagram Reel/post URL.

    Snipivo intentionally accepts only single-post style paths. Profiles,
    stories, login pages, and arbitrary Instagram routes are not accepted.
    """
    url, host, path = _basic_url_checks(raw_url)

    if host not in ALLOWED_INSTAGRAM_HOSTS and not host.endswith(".instagram.com"):
        raise ValueError("That link is not a supported Instagram URL.")

    path_lower = path.lower()
    if not path_lower.startswith(INSTAGRAM_VIDEO_PREFIXES):
        raise ValueError(
            "Paste a public Instagram Reel or post link (for example /reel/... or /p/...)."
        )

    return url


def validate_media_url(raw_url: str) -> tuple[str, Platform]:
    """Validate a supported media URL and identify its platform."""
    url, host, _path = _basic_url_checks(raw_url)

    if host in ALLOWED_TIKTOK_HOSTS or host.endswith(".tiktok.com"):
        return validate_tiktok_url(url), "tiktok"

    if host in ALLOWED_INSTAGRAM_HOSTS or host.endswith(".instagram.com"):
        return validate_instagram_url(url), "instagram"

    raise ValueError("That link is not a supported TikTok or Instagram URL.")
