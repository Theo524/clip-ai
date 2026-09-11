from pathlib import Path

from services.projects import directory_size, load_project, rendered_media, save_project


def test_project_round_trip_and_media_listing(tmp_path: Path):
    job_dir = tmp_path / "job-123"
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True)
    (job_dir / "source.mp4").write_bytes(b"source")
    (clips_dir / "short_demo.mp4").write_bytes(b"short")
    (clips_dir / "clip_demo.mp4").write_bytes(b"clip")

    save_project(job_dir, {"job_id": "job-123", "title": "Demo", "source_type": "upload", "clips": []})
    project = load_project(job_dir)

    assert project is not None
    assert project["title"] == "Demo"
    assert project["created_at"]
    assert project["updated_at"]

    media = rendered_media(job_dir, "job-123")
    assert {item["kind"] for item in media} == {"short", "original"}
    assert directory_size(job_dir) > 0
