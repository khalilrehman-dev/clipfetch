from app.downloader import choose_clean_format


def test_prefers_clean_progressive_format():
    formats = [
        {
            "format_id": "download",
            "format_note": "watermarked",
            "url": "https://cdn.example/logo/main.mp4?logo_type=tiktok",
            "vcodec": "h264",
            "acodec": "aac",
            "ext": "mp4",
            "height": 1080,
        },
        {
            "format_id": "play",
            "format_note": "",
            "url": "https://cdn.example/main.mp4",
            "vcodec": "h264",
            "acodec": "aac",
            "ext": "mp4",
            "height": 720,
        },
    ]
    chosen = choose_clean_format(formats)
    assert chosen is not None
    assert chosen["format_id"] == "play"


def test_returns_none_when_only_watermarked_exists():
    formats = [
        {
            "format_id": "download",
            "format_note": "watermarked",
            "url": "https://cdn.example/logo/main.mp4",
            "vcodec": "h264",
            "acodec": "aac",
        }
    ]
    assert choose_clean_format(formats) is None
