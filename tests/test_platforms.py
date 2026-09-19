import pytest

from app.downloader import (
    DownloaderError,
    _friendly_error,
    _instagram_image_candidates,
    _platform_from_info,
    _unique_urls,
)


def test_detects_tiktok_extractor():
    assert _platform_from_info({"extractor_key": "TikTok"}) == "tiktok"


def test_detects_instagram_extractor():
    assert _platform_from_info({"extractor_key": "Instagram"}) == "instagram"


def test_rejects_unknown_extractor():
    with pytest.raises(DownloaderError):
        _platform_from_info({"extractor_key": "Generic"})


def test_instagram_image_candidates_prefer_display_urls_and_dedupe_sizes():
    html = r'''<meta property="og:image" content="https://scontent.cdninstagram.com/fallback.jpg?x=1">
    <script>{"display_url":"https:\/\/scontent.cdninstagram.com\/a.jpg?x=1",
    "display_url":"https:\/\/scontent.cdninstagram.com\/a.jpg?x=2",
    "display_url":"https:\/\/scontent.cdninstagram.com\/b.jpg?x=3"}</script>'''
    urls = _instagram_image_candidates(html)
    assert len(urls) == 2
    assert "/a.jpg" in urls[0]
    assert "/b.jpg" in urls[1]


def test_unique_urls_ignore_query_variants():
    urls = _unique_urls([
        "https://p16.tiktokcdn.com/a.jpeg?width=720",
        "https://p16.tiktokcdn.com/a.jpeg?width=1080",
        "https://p16.tiktokcdn.com/b.jpeg?width=1080",
    ])
    assert len(urls) == 2


def test_instagram_login_error_is_user_friendly():
    msg = _friendly_error("Login required. Please use cookies.", "instagram")
    assert "private or requires login" in msg
    assert "Instagram" in msg
