import pytest

from app.downloader import DownloaderError, _friendly_error, _platform_from_info, _reject_unsupported_instagram_content


def test_detects_tiktok_extractor():
    assert _platform_from_info({"extractor_key": "TikTok"}) == "tiktok"


def test_detects_instagram_extractor():
    assert _platform_from_info({"extractor_key": "Instagram"}) == "instagram"


def test_rejects_unknown_extractor():
    with pytest.raises(DownloaderError):
        _platform_from_info({"extractor_key": "Generic"})


def test_rejects_instagram_image_only_post():
    with pytest.raises(DownloaderError, match="does not contain a downloadable video"):
        _reject_unsupported_instagram_content({"formats": []})


def test_accepts_instagram_video_format():
    _reject_unsupported_instagram_content(
        {"formats": [{"format_id": "video", "vcodec": "h264", "acodec": "aac"}]}
    )


def test_instagram_login_error_is_user_friendly():
    msg = _friendly_error("Login required. Please use cookies.", "instagram")
    assert "private or requires login" in msg
    assert "Instagram" in msg
