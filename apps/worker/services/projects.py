from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_project(job_dir: Path, payload: dict) -> dict:
    project_path = job_dir / "project.json"
    data = dict(payload)
    if project_path.exists():
        try:
            existing = json.loads(project_path.read_text(encoding="utf-8"))
            existing.update(data)
            data = existing
        except Exception:
            pass
    data.setdefault("created_at", utc_now_iso())
    data["updated_at"] = utc_now_iso()
    project_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load_project(job_dir: Path) -> dict | None:
    project_path = job_dir / "project.json"
    if not project_path.exists():
        return None
    try:
        return json.loads(project_path.read_text(encoding="utf-8"))
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
