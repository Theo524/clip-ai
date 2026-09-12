from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import platform
import shutil
import subprocess
import sys
import zipfile


def _cmd_version(binary: str) -> str | None:
    path = shutil.which(binary)
    if not path:
        return None
    try:
        completed = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
        line = (completed.stdout or completed.stderr or "").splitlines()[0]
        return line[:300]
    except Exception:
        return path


def build_diagnostic_zip(root: Path, destination: Path, *, app_version: str, release_name: str, settings_summary: dict, tasks: list[dict]) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    projects = []
    for job_dir in root.iterdir() if root.exists() else []:
        if not job_dir.is_dir():
            continue
        project = job_dir / "project.json"
        if not project.exists():
            continue
        try:
            data = json.loads(project.read_text(encoding="utf-8"))
            projects.append({
                "job_id": data.get("job_id", job_dir.name),
                "title": data.get("title"),
                "source_type": data.get("source_type"),
                "status": data.get("status"),
                "clip_count": len(data.get("clips") or []),
                "updated_at": data.get("updated_at"),
            })
        except Exception:
            projects.append({"job_id": job_dir.name, "read_error": True})

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clip_ai": {"version": app_version, "release": release_name},
        "system": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "ffmpeg": _cmd_version("ffmpeg"),
            "ffprobe": _cmd_version("ffprobe"),
        },
        "settings": settings_summary,
        "projects": projects,
        "tasks": [
            {k: item.get(k) for k in ("task_id", "kind", "status", "stage", "progress", "job_id", "error", "created_at", "updated_at", "recoverable")}
            for item in tasks[:100]
        ],
        "privacy": "API keys, source paths outside the Clip AI work directory, transcript text and OAuth-style secrets are intentionally excluded.",
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("diagnostics.json", json.dumps(report, ensure_ascii=False, indent=2))
        readme = "Clip AI diagnostic bundle\n\nThis bundle is redacted. It contains versions, project/task status, and system capability information only.\n"
        zf.writestr("README.txt", readme)
    return destination
