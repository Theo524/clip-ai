from __future__ import annotations

import hashlib
import json
from pathlib import Path

from models import TranscriptSegment


_SAMPLE_BYTES = 1024 * 1024


def fast_media_fingerprint(media_path: str) -> str:
    """Create a fast content fingerprint without hashing an entire long video.

    We hash the file size plus the first and last 1 MiB. This is intentionally a
    local-development cache key, not a cryptographic identity guarantee.
    """
    path = Path(media_path)
    stat = path.stat()
    digest = hashlib.sha256()
    digest.update(str(stat.st_size).encode("ascii"))
    with path.open("rb") as handle:
        digest.update(handle.read(_SAMPLE_BYTES))
        if stat.st_size > _SAMPLE_BYTES:
            handle.seek(max(0, stat.st_size - _SAMPLE_BYTES))
            digest.update(handle.read(_SAMPLE_BYTES))
    return digest.hexdigest()


def transcript_cache_key(media_path: str, strategy: str) -> str:
    digest = hashlib.sha256()
    digest.update(fast_media_fingerprint(media_path).encode("ascii"))
    digest.update(b"|")
    digest.update(strategy.encode("utf-8"))
    return digest.hexdigest()


def cache_path(cache_root: Path, key: str) -> Path:
    return cache_root / f"{key}.json"


def load_cached_transcript(cache_root: Path, key: str) -> list[TranscriptSegment] | None:
    path = cache_path(cache_root, key)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        segments = [TranscriptSegment.model_validate(item) for item in raw]
        return segments or None
    except Exception:
        # A corrupt cache should never block a project. Remove it and regenerate.
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def save_cached_transcript(cache_root: Path, key: str, segments: list[TranscriptSegment]) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    path = cache_path(cache_root, key)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps([segment.model_dump() for segment in segments], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)
    return path


def cleanup_transcript_cache(cache_root: Path, *, max_age_days: int = 30, max_bytes: int = 512 * 1024 * 1024) -> dict[str, int]:
    """Bound the disposable cross-project transcript cache by age and total size.

    Per-project transcript.json files are never touched. This cache only exists to
    avoid retranscribing an identical source that is imported again later.
    """
    import time

    if not cache_root.exists():
        return {"removed_files": 0, "removed_bytes": 0}
    removed_files = 0
    removed_bytes = 0
    now = time.time()
    max_age_seconds = max(1, int(max_age_days)) * 86400
    entries = []
    for path in cache_root.glob("*.json"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if now - stat.st_mtime > max_age_seconds:
            try:
                removed_bytes += stat.st_size
                path.unlink()
                removed_files += 1
            except OSError:
                pass
        else:
            entries.append((stat.st_mtime, stat.st_size, path))

    total = sum(size for _mtime, size, _path in entries)
    if total > max_bytes:
        for _mtime, size, path in sorted(entries, key=lambda item: item[0]):
            if total <= max_bytes:
                break
            try:
                path.unlink()
                removed_files += 1
                removed_bytes += size
                total -= size
            except OSError:
                pass
    return {"removed_files": removed_files, "removed_bytes": removed_bytes}
