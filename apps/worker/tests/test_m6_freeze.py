import json
from pathlib import Path
from types import SimpleNamespace

from models import AnalyzeRequest, ProjectCleanupRequest
from services import media
from services.projects import cleanup_project_storage, load_project, save_project, source_available


def test_project_migration_adds_m6_defaults(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    (job / "project.json").write_text(json.dumps({"title": "Old project", "clips": []}), encoding="utf-8")
    data = load_project(job)
    assert data["schema_version"] == 24
    assert data["audio_track"] == 0
    assert data["performance"] == {}


def test_cleanup_project_storage_preserves_finished_outputs(tmp_path):
    job = tmp_path / "job"
    clips = job / "clips"
    exports = job / "exports"
    audio = job / "audio"
    clips.mkdir(parents=True)
    exports.mkdir()
    audio.mkdir()
    (job / "source.mkv").write_bytes(b"source" * 100)
    (job / "normalized.mp4").write_bytes(b"normalized" * 100)
    (job / "transcript.json").write_text("[]", encoding="utf-8")
    save_project(job, {"title": "Keep me", "clips": []})
    (clips / "short_final.mp4").write_bytes(b"short")
    (clips / "cover_final.jpg").write_bytes(b"cover")
    (clips / "preview_test.mp4").write_bytes(b"preview")
    (clips / "captions_test.ass").write_text("subs", encoding="utf-8")
    (clips / "reframe_test.json").write_text("{}", encoding="utf-8")
    (exports / "package.zip").write_bytes(b"zip")
    (audio / "audio_000.mp3").write_bytes(b"audio")

    result = cleanup_project_storage(job, remove_source=True)

    assert result["source_removed"] is True
    assert result["source_available"] is False
    assert not (job / "source.mkv").exists()
    assert not (job / "normalized.mp4").exists()
    assert not (clips / "preview_test.mp4").exists()
    assert not (clips / "captions_test.ass").exists()
    assert not (clips / "reframe_test.json").exists()
    assert (clips / "short_final.mp4").exists()
    assert (clips / "cover_final.jpg").exists()
    assert (job / "transcript.json").exists()
    assert (job / "project.json").exists()
    assert (exports / "package.zip").exists()


def test_cleanup_cache_only_keeps_source(tmp_path):
    job = tmp_path / "job"
    (job / "audio").mkdir(parents=True)
    (job / "source.mp4").write_bytes(b"source")
    (job / "audio" / "audio_000.mp3").write_bytes(b"audio")
    result = cleanup_project_storage(job, remove_source=False)
    assert result["source_removed"] is False
    assert source_available(job) is True
    assert (job / "source.mp4").exists()


def test_probe_media_reports_multiple_audio_tracks(tmp_path, monkeypatch):
    source = tmp_path / "dual.mkv"
    source.write_bytes(b"video")
    payload = {
        "format": {"duration": "60.0", "format_name": "matroska"},
        "streams": [
            {"index": 0, "codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "avg_frame_rate": "24/1"},
            {"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "jpn", "title": "Japanese"}, "disposition": {"default": 1}},
            {"index": 2, "codec_type": "audio", "codec_name": "aac", "channels": 2, "tags": {"language": "eng", "title": "English"}, "disposition": {"default": 0}},
        ],
    }
    monkeypatch.setattr(media.shutil, "which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(media.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""))
    info = media.probe_media(str(source))
    assert info["audio_streams"] == 2
    assert info["default_audio_track"] == 1
    assert info["audio_tracks"][1]["language"] == "eng"
    assert info["audio_tracks"][1]["title"] == "English"


def test_extract_audio_chunks_maps_requested_track(tmp_path, monkeypatch):
    source = tmp_path / "dual.mkv"
    source.write_bytes(b"video")
    output = tmp_path / "audio"
    seen = {}
    monkeypatch.setattr(media, "require_ffmpeg", lambda: None)

    def fake_run(command, action, **kwargs):
        seen["command"] = command
        output.mkdir(parents=True, exist_ok=True)
        (output / "audio_000.mp3").write_bytes(b"audio")

    monkeypatch.setattr(media, "_run_process", fake_run)
    chunks = media.extract_audio_chunks(str(source), str(output), audio_track=2)
    assert chunks
    assert "0:a:1?" in seen["command"]


def test_requests_accept_audio_track_choice():
    cleanup = ProjectCleanupRequest(remove_source=True)
    assert cleanup.remove_source is True


def test_transcript_cache_cleanup_prunes_old_entries(tmp_path, monkeypatch):
    import os
    import time
    from services.transcript_cache import cleanup_transcript_cache
    root = tmp_path / "cache"
    root.mkdir()
    old = root / "old.json"
    new = root / "new.json"
    old.write_bytes(b"x" * 20)
    new.write_bytes(b"y" * 20)
    ancient = time.time() - 40 * 86400
    os.utime(old, (ancient, ancient))
    result = cleanup_transcript_cache(root, max_age_days=30, max_bytes=1024)
    assert result["removed_files"] == 1
    assert not old.exists()
    assert new.exists()
