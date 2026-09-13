from pathlib import Path
import json

from models import TranscriptSegment
from services.profiles import get_processing_profile
from services.projects import load_project, save_project
from services.subtitles_export import to_srt, to_vtt
from services.tasks import TaskManager


def test_processing_profiles_are_bounded():
    low = get_processing_profile("low-memory")
    balanced = get_processing_profile("balanced")
    fast = get_processing_profile("fast")
    assert low.chunk_seconds < balanced.chunk_seconds <= fast.chunk_seconds
    assert low.cpu_threads < fast.cpu_threads
    assert get_processing_profile("unknown").name == "balanced"


def test_subtitle_exports_are_relative_to_clip_start():
    segments = [
        TranscriptSegment(start=10.0, end=12.0, text="Hello there"),
        TranscriptSegment(start=12.2, end=14.0, text="Second line"),
    ]
    srt = to_srt(segments, 10.0, 14.0)
    vtt = to_vtt(segments, 10.0, 14.0)
    assert "00:00:00,000 --> 00:00:02,000" in srt
    assert "WEBVTT" in vtt
    assert "00:00:02.200 --> 00:00:04.000" in vtt


def test_project_migration_adds_v22_context_defaults(tmp_path):
    job = tmp_path / "abc"
    job.mkdir()
    (job / "project.json").write_text(json.dumps({"title": "Old", "clips": []}), encoding="utf-8")
    data = load_project(job)
    assert data["schema_version"] == 24
    assert data["processing_profile"] == "balanced"
    assert data["status"] == "queued"
    assert data["transcript_revision"] == 0
    assert data["content_type"] == "auto"
    assert data["resolved_content_type"] == "other"
    assert data["content_structure"] == "auto"
    assert data["resolved_content_structure"] == "single-story"
    assert data["duration_preference"] == "auto"
    assert data["project_notes"] == ""


def test_project_save_is_merge_safe(tmp_path):
    job = tmp_path / "merge"
    job.mkdir()
    save_project(job, {"title": "Original", "clips": [{"x": 1}]})
    save_project(job, {"status": "ready"})
    data = load_project(job)
    assert data["title"] == "Original"
    assert data["clips"] == [{"x": 1}]
    assert data["status"] == "ready"


def test_task_manager_marks_interrupted_tasks_recoverable(tmp_path):
    root = tmp_path / "work"
    state_dir = root / "_state"
    state_dir.mkdir(parents=True)
    state = {
        "schema": 1,
        "tasks": [{
            "task_id": "t1", "kind": "analysis", "status": "running", "stage": "Transcribing",
            "progress": 44, "message": "x", "job_id": "job1", "result": None, "error": None,
            "recoverable": True, "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }],
    }
    (state_dir / "tasks.json").write_text(json.dumps(state), encoding="utf-8")
    manager = TaskManager()
    manager.configure(root)
    item = manager.get("t1")
    assert item["status"] == "failed"
    assert item["stage"] == "Interrupted"
    assert item["recoverable"] is True
