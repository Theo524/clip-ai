from main import is_youtube_url, safe_download_name


def test_youtube_urls():
    assert is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert is_youtube_url("https://youtu.be/abc")
    assert not is_youtube_url("https://example.com/video")


def test_safe_download_name():
    assert safe_download_name("You’ll Never Feel Ready!") == "Youll-Never-Feel-Ready.mp4"
    assert safe_download_name("  My clip  ") == "My-clip.mp4"
    assert safe_download_name("", "short_v9_123") == "short_v9_123.mp4"
