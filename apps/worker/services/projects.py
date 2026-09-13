from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import shutil
import uuid

PROJECT_SCHEMA_VERSION = 22


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def migrate_project(data: dict, job_id: str | None = None) -> dict:
    """Small, additive migrations so future releases can keep opening old projects."""
    migrated = dict(data or {})
    if job_id:
        migrated.setdefault("job_id", job_id)
    migrated.setdefault("status", "ready" if migrated.get("clips") else "queued")
    migrated.setdefault("processing_profile", "balanced")
    migrated.setdefault("content_type", "auto")
    migrated.setdefault("resolved_content_type", "other")
    migrated.setdefault("content_structure", "auto")
    migrated.setdefault("resolved_content_structure", "single-story")
    migrated.setdefault("subject_hint", None)
    migrated.setdefault("context_confidence", 0.0)
    migrated.setdefault("context_signals", [])
    migrated.setdefault("clips", [])
    migrated.setdefault("transcript_revision", 0)
    migrated["schema_version"] = PROJECT_SCHEMA_VERSION
    return migrated


def save_project(job_dir: Path, payload: dict) -> dict:
    project_path = job_dir / "project.json"
    data = dict(payload)
    if project_path.exists():
        try:
            existing = migrate_project(json.loads(project_path.read_text(encoding="utf-8")), job_dir.name)
            existing.update(data)
            data = existing
        except Exception:
            pass
    data = migrate_project(data, job_dir.name)
    data.setdefault("created_at", utc_now_iso())
    data["updated_at"] = utc_now_iso()
    _atomic_json_write(project_path, data)
    return data


def load_project(job_dir: Path) -> dict | None:
    project_path = job_dir / "project.json"
    if not project_path.exists():
        return None
    try:
        raw = json.loads(project_path.read_text(encoding="utf-8"))
        migrated = migrate_project(raw, job_dir.name)
        if migrated != raw:
            _atomic_json_write(project_path, migrated)
        return migrated
    except Exception:
        return None


def directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def rendered_media(job_dir: Path, job_id: str) -> list[dict]:
    clips_dir = job_dir / "clips"
    if not clips_dir.exists():
        return []

    items: list[dict] = []
    for path in sorted(clips_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = path.stat()
        except OSError:
            continue
        kind = "short" if path.name.startswith("short_") else "original"
        media_url = f"/media/{job_id}/{path.name}"
        items.append(
            {
                "filename": path.name,
                "kind": kind,
                "media_url": media_url,
                "download_url": f"{media_url}?download=true",
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return items


def cleanup_stale_work(root: Path) -> dict[str, int]:
    """Remove disposable leftovers from interrupted/local processing runs.

    Source videos, normalized working copies, transcripts, project metadata and finished
    renders are preserved. Atomic `.part`/`.tmp` outputs and transcripted audio chunks
    are safe to remove.
    """
    removed_files = 0
    removed_audio_dirs = 0
    if not root.exists():
        return {"temp_files": 0, "audio_dirs": 0}

    for pattern in ("*.part.*", ".*.tmp", "*.tmp"):
        for path in root.rglob(pattern):
            if path.is_file():
                try:
                    path.unlink()
                    removed_files += 1
                except OSError:
                    pass

    for job_dir in root.iterdir():
        if not job_dir.is_dir() or job_dir.name.startswith("_"):
            continue
        audio_dir = job_dir / "audio"
        transcript = job_dir / "transcript.json"
        if audio_dir.exists() and transcript.exists():
            try:
                shutil.rmtree(audio_dir)
                removed_audio_dirs += 1
            except OSError:
                pass

    return {"temp_files": removed_files, "audio_dirs": removed_audio_dirs}
