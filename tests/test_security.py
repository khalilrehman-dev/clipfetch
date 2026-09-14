import pytest

from app.security import validate_tiktok_url


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


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/video/123",
        "file:///etc/passwd",
        "http://127.0.0.1/admin",
        "https://tiktok.com.evil.example/video/123",
    ],
)
def test_blocks_non_tiktok_urls(url):
    with pytest.raises(ValueError):
        validate_tiktok_url(url)
