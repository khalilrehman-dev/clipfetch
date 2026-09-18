import pytest

from app.security import validate_instagram_url, validate_media_url, validate_tiktok_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tiktok.com/@creator/video/123",
        "https://vm.tiktok.com/abc123/",
        "https://vt.tiktok.com/abc123/",
        "https://www.tiktokv.com/share/video/123/",
    ],
)
def test_allows_tiktok_urls(url):
    assert validate_tiktok_url(url) == url
    clean, platform = validate_media_url(url)
    assert clean == url
    assert platform == "tiktok"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/reel/ABC123/",
        "https://instagram.com/p/ABC123/?igsh=test",
        "https://www.instagram.com/tv/ABC123/",
        "https://www.instagram.com/share/reel/ABC123/",
    ],
)
def test_allows_instagram_video_urls(url):
    assert validate_instagram_url(url) == url
    clean, platform = validate_media_url(url)
    assert clean == url
    assert platform == "instagram"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/snipivo/",
        "https://www.instagram.com/stories/snipivo/123/",
        "https://www.instagram.com/explore/",
    ],
)
def test_blocks_unsupported_instagram_routes(url):
    with pytest.raises(ValueError):
        validate_instagram_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video/123",
        "file:///etc/passwd",
        "http://127.0.0.1/admin",
        "https://tiktok.com.evil.example/video/123",
        "https://instagram.com.evil.example/reel/ABC123/",
        "https://user:pass@instagram.com/reel/ABC123/",
    ],
)
def test_blocks_non_supported_urls(url):
    with pytest.raises(ValueError):
        validate_media_url(url)
