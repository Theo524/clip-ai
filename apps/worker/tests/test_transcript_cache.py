from pathlib import Path

from models import TranscriptSegment
from services.transcript_cache import (
    fast_media_fingerprint,
    load_cached_transcript,
    save_cached_transcript,
    transcript_cache_key,
)


def test_transcript_cache_round_trip(tmp_path: Path):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"abc123" * 200)
    cache = tmp_path / "cache"
    segments = [TranscriptSegment(start=0.0, end=1.5, text="hello world")]

    key = transcript_cache_key(str(media), "local:tiny.en:int8:test")
    save_cached_transcript(cache, key, segments)
    loaded = load_cached_transcript(cache, key)

    assert loaded is not None
    assert loaded[0].text == "hello world"
    assert loaded[0].end == 1.5


def test_fast_fingerprint_changes_when_media_changes(tmp_path: Path):
    media = tmp_path / "video.mp4"
    media.write_bytes(b"first")
    first = fast_media_fingerprint(str(media))
    media.write_bytes(b"second")
    second = fast_media_fingerprint(str(media))
    assert first != second
