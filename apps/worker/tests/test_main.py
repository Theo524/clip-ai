from main import is_youtube_url, safe_download_name


def test_youtube_urls():
    assert is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert is_youtube_url("https://youtu.be/abc")
    assert not is_youtube_url("https://example.com/video")


def test_safe_download_name():
    assert safe_download_name("You’ll Never Feel Ready!") == "Youll-Never-Feel-Ready.mp4"
    assert safe_download_name("  My clip  ") == "My-clip.mp4"
    assert safe_download_name("", "short_v9_123") == "short_v9_123.mp4"


def test_v20_preflight_metadata():
    from main import APP_VERSION, RELEASE_NAME, _system_preflight

    data = _system_preflight()
    assert APP_VERSION.startswith("20.")
    assert data.version == APP_VERSION
    assert data.release == RELEASE_NAME
    assert {item.id for item in data.checks} >= {"ffmpeg", "ffprobe", "workspace", "transcription", "ranking", "disk"}


def test_v20_preflight_has_storage_numbers():
    from main import _system_preflight

    data = _system_preflight()
    assert data.disk_total_bytes > 0
    assert data.disk_free_bytes >= 0
    assert data.project_count >= 0
    assert data.project_storage_bytes >= 0
