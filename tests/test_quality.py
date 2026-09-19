from app.downloader import _audio_quality_options, _video_format_selector, _video_quality_options


def test_video_quality_options_only_show_available_levels():
    formats = [
        {"format_id": "a", "vcodec": "h264", "acodec": "aac", "width": 1080, "height": 1920, "filesize": 12_000_000},
        {"format_id": "b", "vcodec": "h264", "acodec": "aac", "width": 720, "height": 1280, "filesize": 7_000_000},
        {"format_id": "c", "vcodec": "h264", "acodec": "aac", "width": 540, "height": 960, "filesize": 4_000_000},
    ]
    options = _video_quality_options(formats)
    assert [item["value"] for item in options] == ["best", "1080", "720"]
    assert options[1]["approx_bytes"] == 12_000_000


def test_video_quality_hides_1080_when_source_is_720():
    formats = [
        {"format_id": "b", "vcodec": "h264", "width": 720, "height": 1280},
        {"format_id": "c", "vcodec": "h264", "width": 480, "height": 854},
    ]
    assert [item["value"] for item in _video_quality_options(formats)] == ["best", "720"]


def test_audio_quality_estimates_size_from_duration():
    options = _audio_quality_options(60)
    assert [item["value"] for item in options] == [128, 192, 320]
    assert options[1]["approx_bytes"] == 1_440_000


def test_instagram_720_selector_uses_matching_portrait_format():
    info = {"formats": [
        {"format_id": "1080", "vcodec": "h264", "acodec": "none", "width": 1080, "height": 1920, "ext": "mp4"},
        {"format_id": "720", "vcodec": "h264", "acodec": "aac", "width": 720, "height": 1280, "ext": "mp4"},
    ]}
    selector = _video_format_selector(info, "instagram", "720")
    assert selector.startswith("720/")


def test_specific_video_only_format_merges_best_audio():
    info = {"formats": [
        {"format_id": "v1080", "vcodec": "h264", "acodec": "none", "width": 1080, "height": 1920, "ext": "mp4"},
    ]}
    selector = _video_format_selector(info, "instagram", "1080")
    assert "v1080+bestaudio" in selector
