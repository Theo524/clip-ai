from pathlib import Path

import main
from models import ClipCandidate, TranscriptSegment


def test_empty_vad_chunk_retries_without_vad(tmp_path, monkeypatch):
    media = tmp_path / "quiet.mp4"
    media.write_bytes(b"not-a-real-video-but-enough-for-cache-key")
    monkeypatch.setattr(main.settings, "work_dir", str(tmp_path / "work"))
    monkeypatch.setattr(main.settings, "transcription_backend", "local")
    monkeypatch.setattr(main, "probe_media", lambda _path: {"has_video": True, "has_audio": True, "duration": 180.0, "audio_codec": "aac", "video_codec": "h264", "fps": 30.0, "rotation": 0, "size_bytes": media.stat().st_size})
    monkeypatch.setattr(main, "should_normalize_media", lambda _info, _path: (False, []))
    monkeypatch.setattr(main, "extract_audio_chunks", lambda *args, **kwargs: [str(tmp_path / "audio_000.mp3")])

    calls = []

    def fake_transcribe(_path, offset_seconds=0.0, *, vad_filter=True, cpu_threads=None):
        calls.append(vad_filter)
        if vad_filter:
            return []
        return [TranscriptSegment(start=0.0, end=4.0, text="Quiet English dialogue is here.")]

    monkeypatch.setattr(main, "_transcribe_chunk", fake_transcribe)
    monkeypatch.setattr(
        main,
        "_rank_segments",
        lambda _segments, max_clips, **_kwargs: [
            ClipCandidate(start=0.0, end=4.0, title="Quiet dialogue", hook="Quiet English dialogue", score=80, reasons=["clear thought"])
        ],
    )

    result = main.analyze_local_media(str(media), "quiet.mp4", 3, job_id="quiet-test")
    assert result.clips
    assert calls == [True, False]
    assert (tmp_path / "work" / "quiet-test" / "transcript.json").exists()


def test_same_media_reuses_transcript_cache(tmp_path, monkeypatch):
    media = tmp_path / "repeat.mp4"
    media.write_bytes(b"same-video-content" * 100)
    monkeypatch.setattr(main.settings, "work_dir", str(tmp_path / "work"))
    monkeypatch.setattr(main.settings, "transcription_backend", "local")
    monkeypatch.setattr(main, "probe_media", lambda _path: {"has_video": True, "has_audio": True, "duration": 120.0, "audio_codec": "aac", "video_codec": "h264", "fps": 30.0, "rotation": 0, "size_bytes": media.stat().st_size})
    monkeypatch.setattr(main, "should_normalize_media", lambda _info, _path: (False, []))
    monkeypatch.setattr(main, "extract_audio_chunks", lambda *args, **kwargs: [str(tmp_path / "audio_000.mp3")])
    monkeypatch.setattr(
        main,
        "_rank_segments",
        lambda _segments, max_clips, **_kwargs: [
            ClipCandidate(start=0.0, end=4.0, title="Cached", hook="Cache me", score=80, reasons=["clear thought"])
        ],
    )

    calls = {"count": 0}

    def first_transcribe(_path, offset_seconds=0.0, *, vad_filter=True, cpu_threads=None):
        calls["count"] += 1
        return [TranscriptSegment(start=0.0, end=4.0, text="Cache this English dialogue.")]

    monkeypatch.setattr(main, "_transcribe_chunk", first_transcribe)
    main.analyze_local_media(str(media), "repeat.mp4", 3, job_id="cache-first")
    assert calls["count"] == 1

    def should_not_transcribe(*_args, **_kwargs):
        raise AssertionError("Whisper should not run when a transcript cache exists")

    monkeypatch.setattr(main, "_transcribe_chunk", should_not_transcribe)
    second = main.analyze_local_media(str(media), "repeat.mp4", 3, job_id="cache-second")
    assert second.clips
