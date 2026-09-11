from pathlib import Path
from concurrent.futures import CancelledError
import json
import importlib.util
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import re
import shutil
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models import AnalyzeRequest, AnalyzeResponse, CleanupResponse, ClipCandidate, ClipCopyGenerateRequest, ClipCopyResponse, ClipCopyUpdateRequest, ProjectDetail, ProjectSummary, RenderClipRequest, RenderClipResponse, SystemCheck, SystemPreflightResponse, TaskCreateResponse, TaskStatusResponse, TranscriptSegment, YouTubeInfoResponse
from settings import settings
from services.media import cut_clip, extract_audio_chunks, extract_cover_frame, probe_media_audio, render_adaptive_short
from services.captions import write_clip_ass
from services.mock import mock_clips
from services.reframe import ReframePlan, load_reframe_plan, plan_smart_reframe, save_reframe_plan
from services.layouts import auto_profile, choose_caption_style, choose_caption_zone, choose_frame_size, choose_layout
from services.projects import cleanup_stale_work, directory_size, load_project, rendered_media, save_project
from services.copywriter import dialogue_for_range, generate_clip_copy_local
from services.tasks import tasks
from services.transcript_cache import load_cached_transcript, save_cached_transcript, transcript_cache_key

APP_VERSION = "20.1.0-beta.1"
RELEASE_NAME = "Beta Reliability Patch"

app = FastAPI(title="Clip AI Worker", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_.-]+$")

# Clean leftovers from interrupted local runs when the worker starts.
STARTUP_CLEANUP = cleanup_stale_work(Path(settings.work_dir))


def safe_download_name(value: str | None, fallback: str = "clip-ai-short") -> str:
    """Return a browser-safe, human-readable MP4 download filename."""
    raw = (value or "").strip()
    if raw.lower().endswith(".mp4"):
        raw = raw[:-4]
    clean = re.sub(r"[^A-Za-z0-9 _-]+", "", raw)
    clean = re.sub(r"[ _]+", "-", clean).strip("-_")[:80]
    if not clean:
        clean = re.sub(r"[^A-Za-z0-9_-]+", "-", fallback).strip("-_") or "clip-ai-short"
    return f"{clean}.mp4"


def is_youtube_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def fetch_youtube_info(source_url: str) -> YouTubeInfoResponse:
    if not is_youtube_url(source_url):
        raise HTTPException(status_code=400, detail="Enter a valid YouTube URL.")

    endpoint = "https://www.youtube.com/oembed?" + urlencode({"url": source_url, "format": "json"})
    request = Request(endpoint, headers={"User-Agent": f"ClipAI/{APP_VERSION}"})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Clip AI could not read this YouTube video's public metadata. Check the link and your internet connection.",
        ) from exc

    return YouTubeInfoResponse(
        source_url=source_url,
        title=str(payload.get("title") or "YouTube video"),
        author_name=payload.get("author_name"),
        thumbnail_url=payload.get("thumbnail_url"),
        provider_name=str(payload.get("provider_name") or "YouTube"),
    )


def _job_dir(job_id: str) -> Path:
    if not SAFE_ID.fullmatch(job_id):
        raise HTTPException(status_code=400, detail="Invalid job id.")
    return Path(settings.work_dir) / job_id


def _find_source(job_id: str) -> Path:
    job_dir = _job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="This analysis job no longer exists.")

    sources = sorted(path for path in job_dir.glob("source.*") if path.is_file())
    if not sources:
        raise HTTPException(status_code=404, detail="Original source video was not found for this job.")
    return sources[0]


def _load_transcript(job_id: str) -> list[TranscriptSegment]:
    transcript_path = _job_dir(job_id) / "transcript.json"
    if not transcript_path.exists():
        raise HTTPException(
            status_code=409,
            detail="This job predates caption storage. Re-analyze the video once, then generate the Short.",
        )
    try:
        raw = json.loads(transcript_path.read_text(encoding="utf-8"))
        return [TranscriptSegment.model_validate(item) for item in raw]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stored transcript could not be read: {exc}") from exc


def _transcribe_chunk(chunk_path: str, offset_seconds: float, *, vad_filter: bool = True):
    backend = settings.transcription_backend.lower().strip()

    if backend == "local":
        from services.transcribe import transcribe_local_with_timestamps
        return transcribe_local_with_timestamps(
            chunk_path,
            model_name=settings.local_whisper_model,
            device=settings.local_whisper_device,
            compute_type=settings.local_whisper_compute_type,
            offset_seconds=offset_seconds,
            vad_filter=vad_filter,
            cpu_threads=settings.local_whisper_cpu_threads,
        )

    if backend == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when TRANSCRIPTION_BACKEND=openai.")
        from services.transcribe import transcribe_openai_with_timestamps
        return transcribe_openai_with_timestamps(
            chunk_path,
            settings.openai_api_key,
            model=settings.openai_transcribe_model,
            offset_seconds=offset_seconds,
        )

    raise RuntimeError("TRANSCRIPTION_BACKEND must be 'local' or 'openai'.")


def _transcription_strategy() -> str:
    backend = settings.transcription_backend.lower().strip()
    if backend == "local":
        return f"local:{settings.local_whisper_model}:{settings.local_whisper_compute_type}:word-v20.1"
    return f"openai:{settings.openai_transcribe_model}:word-v20.1"


def _eta_text(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"about {max(1, seconds)} sec remaining"
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"about {minutes} min remaining"
    hours = minutes // 60
    remainder = minutes % 60
    return f"about {hours} hr {remainder} min remaining" if remainder else f"about {hours} hr remaining"


def _rank_segments(segments, max_clips: int):
    backend = settings.ranking_backend.lower().strip()

    if backend == "local":
        from services.local_rank import rank_clip_candidates_local
        return rank_clip_candidates_local(segments, max_clips=max_clips)

    if backend == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when RANKING_BACKEND=openai.")
        from services.rank import rank_clip_candidates
        return rank_clip_candidates(
            segments=segments,
            api_key=settings.openai_api_key,
            model=settings.openai_rank_model,
            max_clips=max_clips,
        )

    raise RuntimeError("RANKING_BACKEND must be 'local' or 'openai'.")


def analyze_local_media(
    media_path: str,
    source_label: str,
    max_clips: int,
    *,
    job_id: str | None = None,
    project_title: str | None = None,
    source_type: str = "upload",
    author_name: str | None = None,
    thumbnail_url: str | None = None,
    progress=None,
    cancel_event=None,
) -> AnalyzeResponse:
    resolved_job_id = job_id or str(uuid.uuid4())
    job_dir = _job_dir(resolved_job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = job_dir / "audio"

    def notify(value: int, stage: str, message: str) -> None:
        if progress is not None:
            progress(value, stage, message)

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()

    try:
        check_cancel()
        notify(4, "Checking media", "Checking the video's audio track…")
        media_info = probe_media_audio(media_path)
        if not media_info.get("has_audio"):
            raise RuntimeError("This video has no audio track. Clip AI needs spoken audio to find clip moments.")

        duration = float(media_info.get("duration") or 0.0)
        # Ten-minute chunks give long videos more useful progress/cancel checkpoints without
        # multiplying model loads. Short videos keep the user's configured chunk size.
        effective_chunk_seconds = settings.audio_chunk_seconds
        if duration >= 1800:
            effective_chunk_seconds = min(effective_chunk_seconds, 600)

        transcript_path = job_dir / "transcript.json"
        cache_root = Path(settings.work_dir) / "cache" / "transcripts"
        cache_key = transcript_cache_key(media_path, _transcription_strategy())
        segments: list[TranscriptSegment] = []

        if transcript_path.exists():
            try:
                raw = json.loads(transcript_path.read_text(encoding="utf-8"))
                segments = [TranscriptSegment.model_validate(item) for item in raw]
            except Exception:
                segments = []
            if segments:
                notify(64, "Using saved transcript", "This project was already transcribed, so Clip AI skipped Whisper.")

        if not segments:
            cached = load_cached_transcript(cache_root, cache_key)
            if cached:
                segments = cached
                notify(64, "Using transcript cache", "This same video was transcribed before, so Clip AI reused the cached transcript.")

        if not segments:
            notify(6, "Preparing audio", "Extracting lightweight 16 kHz mono speech audio…")
            if audio_dir.exists():
                shutil.rmtree(audio_dir, ignore_errors=True)
            chunks = extract_audio_chunks(
                media_path,
                str(audio_dir),
                chunk_seconds=effective_chunk_seconds,
                cancel_event=cancel_event,
            )

            total_chunks = max(1, len(chunks))
            chunk_times: list[float] = []
            for index, chunk_path in enumerate(chunks):
                check_cancel()
                pct = 18 + int((index / total_chunks) * 46)
                suffix = ""
                if chunk_times:
                    average = sum(chunk_times) / len(chunk_times)
                    suffix = f" · {_eta_text(average * (total_chunks - index))}"
                notify(pct, "Transcribing", f"Chunk {index + 1} of {total_chunks}{suffix}")
                started = time.monotonic()
                chunk_segments = _transcribe_chunk(
                    chunk_path,
                    offset_seconds=index * effective_chunk_seconds,
                    vad_filter=True,
                )
                # VAD is excellent for speed but can reject quiet film dialogue/music-heavy
                # mixes. An empty chunk gets one automatic full-audio retry.
                if not chunk_segments and settings.transcription_backend.lower().strip() == "local":
                    notify(pct, "Retrying quiet audio", f"Chunk {index + 1} looked silent. Retrying without the speech filter…")
                    check_cancel()
                    chunk_segments = _transcribe_chunk(
                        chunk_path,
                        offset_seconds=index * effective_chunk_seconds,
                        vad_filter=False,
                    )
                chunk_times.append(max(0.01, time.monotonic() - started))
                segments.extend(chunk_segments)
                completed_pct = 18 + int(((index + 1) / total_chunks) * 46)
                if index + 1 < total_chunks:
                    average = sum(chunk_times) / len(chunk_times)
                    notify(completed_pct, "Transcribing", f"Finished chunk {index + 1} of {total_chunks} · {_eta_text(average * (total_chunks - index - 1))}")

        check_cancel()
        if not segments:
            raise RuntimeError(
                "No English speech could be transcribed. Clip AI retried without the silence filter; check that the dialogue is audible and not muted or extremely quiet."
            )

        notify(68, "Saving transcript", "Saving word-level timestamps and transcript cache…")
        transcript_path.write_text(
            json.dumps([segment.model_dump() for segment in segments], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        save_cached_transcript(cache_root, cache_key, segments)

        check_cancel()
        notify(74, "Finding moments", "Ranking the strongest standalone moments…")
        clips = _rank_segments(segments, max_clips=max_clips)

        notify(84, "Writing titles", "Creating dialogue-based titles and post captions…")
        for idx, clip in enumerate(clips):
            check_cancel()
            dialogue = dialogue_for_range(segments, clip.start, clip.end)
            generated = generate_clip_copy_local(dialogue or clip.hook, "auto")
            if settings.ranking_backend.lower().strip() == "local" or not clip.title.strip():
                clip.title = generated.title
            clip.social_caption = generated.social_caption
            if clips:
                notify(84 + int(((idx + 1) / len(clips)) * 8), "Writing titles", f"Polishing clip {idx + 1} of {len(clips)}…")

        check_cancel()
        notify(94, "Saving project", "Saving the project so it can be reopened later…")
        save_project(
            job_dir,
            {
                "job_id": resolved_job_id,
                "title": project_title or Path(media_path).name,
                "source_type": source_type,
                "source_url": source_label if source_type == "youtube" else None,
                "author_name": author_name,
                "thumbnail_url": thumbnail_url,
                "clips": [clip.model_dump() for clip in clips],
            },
        )
        notify(98, "Cleaning up", "Removing temporary audio files…")
        if settings.cleanup_temp_audio and audio_dir.exists():
            shutil.rmtree(audio_dir, ignore_errors=True)

        return AnalyzeResponse(
            source_url=source_label,
            mock=False,
            clips=clips,
            job_id=resolved_job_id,
        )
    except CancelledError:
        if audio_dir.exists():
            shutil.rmtree(audio_dir, ignore_errors=True)
        raise
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        if settings.cleanup_temp_audio and audio_dir.exists():
            shutil.rmtree(audio_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


def _system_preflight() -> SystemPreflightResponse:
    root = Path(settings.work_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    checks: list[SystemCheck] = []

    def add(check_id: str, label: str, ok: bool, detail: str, severity: str = "required"):
        checks.append(SystemCheck(id=check_id, label=label, ok=ok, detail=detail, severity=severity))

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    add("ffmpeg", "FFmpeg", bool(ffmpeg), ffmpeg or "FFmpeg is not available on PATH.")
    add("ffprobe", "FFprobe", bool(ffprobe), ffprobe or "FFprobe is not available on PATH.")

    try:
        probe = root / ".clipai-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        work_ok = True
        work_detail = f"Writable workspace: {root}"
    except OSError as exc:
        work_ok = False
        work_detail = f"Workspace is not writable: {exc}"
    add("workspace", "Local workspace", work_ok, work_detail)

    transcribe_backend = settings.transcription_backend.lower().strip()
    if transcribe_backend == "local":
        local_stt_ok = importlib.util.find_spec("faster_whisper") is not None
        add("transcription", "Local transcription", local_stt_ok, f"faster-whisper · {settings.local_whisper_model}" if local_stt_ok else "faster-whisper is not installed.")
    elif transcribe_backend == "openai":
        add("transcription", "OpenAI transcription", bool(settings.openai_api_key), "API key configured." if settings.openai_api_key else "OPENAI_API_KEY is missing.")
    else:
        add("transcription", "Transcription backend", False, f"Unknown backend: {settings.transcription_backend}")

    ranking_backend = settings.ranking_backend.lower().strip()
    if ranking_backend == "local":
        add("ranking", "Local clip ranking", True, "Local moment ranking is enabled.")
    elif ranking_backend == "openai":
        add("ranking", "OpenAI clip ranking", bool(settings.openai_api_key), "API key configured." if settings.openai_api_key else "OPENAI_API_KEY is missing.")
    else:
        add("ranking", "Ranking backend", False, f"Unknown backend: {settings.ranking_backend}")

    cv2_ok = importlib.util.find_spec("cv2") is not None
    add("vision", "Smart reframing", cv2_ok, "OpenCV is available." if cv2_ok else "OpenCV is not installed.", "warning")

    usage = shutil.disk_usage(root)
    free_gb = usage.free / (1024 ** 3)
    disk_ok = free_gb >= 2.0
    add("disk", "Free disk space", disk_ok, f"{free_gb:.1f} GB free.", "warning" if disk_ok else "required")

    project_count = 0
    project_storage = 0
    if root.exists():
        for job_dir in root.iterdir():
            if not job_dir.is_dir() or not (job_dir / "project.json").exists():
                continue
            project_count += 1
            project_storage += directory_size(job_dir)

    required_ok = all(item.ok for item in checks if item.severity == "required")
    privacy = (
        "Local transcription and ranking are enabled; source video processing stays on this PC."
        if transcribe_backend == "local" and ranking_backend == "local"
        else "One or more AI backends are configured to use an external API."
    )
    return SystemPreflightResponse(
        version=APP_VERSION,
        release=RELEASE_NAME,
        ready=required_ok,
        checks=checks,
        transcription_backend=settings.transcription_backend,
        ranking_backend=settings.ranking_backend,
        local_whisper_model=settings.local_whisper_model,
        work_dir=str(root),
        project_count=project_count,
        project_storage_bytes=project_storage,
        disk_free_bytes=usage.free,
        disk_total_bytes=usage.total,
        privacy_note=privacy,
    )


@app.get("/system/preflight", response_model=SystemPreflightResponse)
def system_preflight():
    return _system_preflight()


@app.post("/system/cleanup", response_model=CleanupResponse)
def system_cleanup():
    root = Path(settings.work_dir).resolve()
    before = directory_size(root)
    cleanup = cleanup_stale_work(root)
    after = directory_size(root)
    return CleanupResponse(
        removed_files=int(cleanup.get("temp_files", 0)) + int(cleanup.get("audio_dirs", 0)),
        removed_bytes=max(0, before - after),
        startup_cleanup=int(STARTUP_CLEANUP.get("temp_files", 0)) + int(STARTUP_CLEANUP.get("audio_dirs", 0)),
    )


@app.get("/health")
def health():
    return {
        "ok": True,
        "version": APP_VERSION,
        "release": RELEASE_NAME,
        "mock_mode": settings.mock_mode,
        "transcription_backend": settings.transcription_backend,
        "ranking_backend": settings.ranking_backend,
        "local_whisper_model": settings.local_whisper_model,
        "api_key_configured": bool(settings.openai_api_key),
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "word_timestamps": True,
        "async_tasks": True,
        "cancellable_ffmpeg": True,
        "cleanup_temp_audio": settings.cleanup_temp_audio,
        "startup_cleanup": STARTUP_CLEANUP,
    }


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str):
    record = tasks.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskStatusResponse.model_validate(record)


@app.post("/tasks/{task_id}/cancel", response_model=TaskStatusResponse)
def cancel_task(task_id: str):
    record = tasks.cancel(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskStatusResponse.model_validate(record)


@app.get("/youtube-info", response_model=YouTubeInfoResponse)
def youtube_info(url: str = Query(..., min_length=10, max_length=2048)):
    return fetch_youtube_info(url)


@app.post("/analyze-youtube-owned", response_model=AnalyzeResponse)
async def analyze_youtube_owned(
    source_url: str = Form(...),
    rights_confirmed: bool = Form(...),
    file: UploadFile = File(...),
    max_clips: int = Form(default=6),
    title: str | None = Form(default=None),
    author_name: str | None = Form(default=None),
    thumbnail_url: str | None = Form(default=None),
):
    if not is_youtube_url(source_url):
        raise HTTPException(status_code=400, detail="Enter a valid YouTube URL.")
    if not rights_confirmed:
        raise HTTPException(status_code=422, detail="Confirm that you own this video or have permission to process it.")
    if max_clips < 1 or max_clips > 12:
        raise HTTPException(status_code=422, detail="max_clips must be between 1 and 12.")
    if settings.mock_mode:
        raise HTTPException(status_code=409, detail="Real analysis is disabled while MOCK_MODE=true.")

    filename = file.filename or "video.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Choose an MP4, MOV, MKV, WEBM, M4V or AVI source file.")

    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_path = job_dir / f"source{suffix}"

    try:
        with saved_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
    finally:
        await file.close()

    (job_dir / "youtube_source.json").write_text(
        json.dumps({"source_url": source_url, "source_filename": filename}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return analyze_local_media(
        str(saved_path),
        source_url,
        max_clips,
        job_id=job_id,
        project_title=title or filename,
        source_type="youtube",
        author_name=author_name,
        thumbnail_url=thumbnail_url,
    )


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    source_url = str(request.source_url)
    if not is_youtube_url(source_url):
        raise HTTPException(status_code=400, detail="Enter a YouTube URL.")

    if settings.mock_mode:
        return AnalyzeResponse(
            source_url=source_url,
            mock=True,
            clips=mock_clips(request.max_clips),
            job_id=None,
        )

    if not request.local_media_path:
        raise HTTPException(
            status_code=422,
            detail="Direct YouTube ingestion is not connected yet. Upload an authorised video file for real analysis.",
        )

    return analyze_local_media(request.local_media_path, source_url, request.max_clips)


@app.post("/tasks/analyze-upload", response_model=TaskCreateResponse, status_code=202)
async def start_analyze_upload_task(
    file: UploadFile = File(...),
    max_clips: int = Form(default=6),
):
    if max_clips < 1 or max_clips > 12:
        raise HTTPException(status_code=422, detail="max_clips must be between 1 and 12.")
    if settings.mock_mode:
        raise HTTPException(status_code=409, detail="Real uploads are disabled while MOCK_MODE=true.")
    filename = file.filename or "video.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload MP4, MOV, MKV, WEBM, M4V or AVI video files.")

    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_path = job_dir / f"source{suffix}"
    try:
        with saved_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
    finally:
        await file.close()

    def runner(task_id, cancel_event):
        return analyze_local_media(
            str(saved_path), filename, max_clips,
            job_id=job_id, project_title=filename, source_type="upload",
            progress=lambda pct, stage, message: tasks.progress(task_id, pct, stage, message),
            cancel_event=cancel_event,
        )

    record = tasks.create("analysis", runner, job_id=job_id)
    return TaskCreateResponse(task_id=record["task_id"], job_id=job_id, status=record["status"])


@app.post("/tasks/analyze-youtube-owned", response_model=TaskCreateResponse, status_code=202)
async def start_analyze_youtube_task(
    source_url: str = Form(...),
    rights_confirmed: bool = Form(...),
    file: UploadFile = File(...),
    max_clips: int = Form(default=6),
    title: str | None = Form(default=None),
    author_name: str | None = Form(default=None),
    thumbnail_url: str | None = Form(default=None),
):
    if not is_youtube_url(source_url):
        raise HTTPException(status_code=400, detail="Enter a valid YouTube URL.")
    if not rights_confirmed:
        raise HTTPException(status_code=422, detail="Confirm that you own this video or have permission to process it.")
    if max_clips < 1 or max_clips > 12:
        raise HTTPException(status_code=422, detail="max_clips must be between 1 and 12.")
    if settings.mock_mode:
        raise HTTPException(status_code=409, detail="Real analysis is disabled while MOCK_MODE=true.")

    filename = file.filename or "video.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Choose an MP4, MOV, MKV, WEBM, M4V or AVI source file.")

    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_path = job_dir / f"source{suffix}"
    try:
        with saved_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
    finally:
        await file.close()
    (job_dir / "youtube_source.json").write_text(
        json.dumps({"source_url": source_url, "source_filename": filename}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    def runner(task_id, cancel_event):
        return analyze_local_media(
            str(saved_path), source_url, max_clips,
            job_id=job_id, project_title=title or filename, source_type="youtube",
            author_name=author_name, thumbnail_url=thumbnail_url,
            progress=lambda pct, stage, message: tasks.progress(task_id, pct, stage, message),
            cancel_event=cancel_event,
        )

    record = tasks.create("analysis", runner, job_id=job_id)
    return TaskCreateResponse(task_id=record["task_id"], job_id=job_id, status=record["status"])


@app.post("/analyze-upload", response_model=AnalyzeResponse)
async def analyze_upload(
    file: UploadFile = File(...),
    max_clips: int = Form(default=6),
):
    if max_clips < 1 or max_clips > 12:
        raise HTTPException(status_code=422, detail="max_clips must be between 1 and 12.")

    filename = file.filename or "video.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Upload MP4, MOV, MKV, WEBM, M4V or AVI video files.",
        )

    if settings.mock_mode:
        raise HTTPException(
            status_code=409,
            detail="Real uploads are disabled while MOCK_MODE=true. Set MOCK_MODE=false in apps/worker/.env and restart the worker.",
        )

    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_path = job_dir / f"source{suffix}"

    try:
        with saved_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
    finally:
        await file.close()

    return analyze_local_media(
        str(saved_path),
        filename,
        max_clips,
        job_id=job_id,
        project_title=filename,
        source_type="upload",
    )


def _project_summary(job_dir: Path, data: dict) -> ProjectSummary:
    job_id = str(data.get("job_id") or job_dir.name)
    renders = rendered_media(job_dir, job_id)
    clips = data.get("clips") or []
    return ProjectSummary(
        job_id=job_id,
        title=str(data.get("title") or "Untitled project"),
        source_type="youtube" if data.get("source_type") == "youtube" else "upload",
        source_url=data.get("source_url"),
        author_name=data.get("author_name"),
        thumbnail_url=data.get("thumbnail_url"),
        created_at=str(data.get("created_at") or data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        updated_at=str(data.get("updated_at") or data.get("created_at") or datetime.now(timezone.utc).isoformat()),
        clip_count=len(clips),
        render_count=len(renders),
        storage_bytes=directory_size(job_dir),
    )


@app.get("/projects", response_model=list[ProjectSummary])
def list_projects():
    root = Path(settings.work_dir)
    if not root.exists():
        return []
    projects: list[ProjectSummary] = []
    for job_dir in root.iterdir():
        if not job_dir.is_dir() or not SAFE_ID.fullmatch(job_dir.name):
            continue
        data = load_project(job_dir)
        if data is None:
            continue
        projects.append(_project_summary(job_dir, data))
    projects.sort(key=lambda item: item.updated_at, reverse=True)
    return projects


@app.get("/projects/{job_id}", response_model=ProjectDetail)
def get_project(job_id: str):
    job_dir = _job_dir(job_id)
    data = load_project(job_dir)
    if data is None:
        raise HTTPException(status_code=404, detail="Saved project not found.")
    summary = _project_summary(job_dir, data)
    return ProjectDetail(
        **summary.model_dump(),
        clips=data.get("clips") or [],
        renders=rendered_media(job_dir, job_id),
    )


def _saved_clip(job_id: str, clip_index: int) -> tuple[Path, dict, ClipCandidate]:
    job_dir = _job_dir(job_id)
    data = load_project(job_dir)
    if data is None:
        raise HTTPException(status_code=404, detail="Saved project not found.")
    raw_clips = data.get("clips") or []
    if clip_index < 0 or clip_index >= len(raw_clips):
        raise HTTPException(status_code=404, detail="Saved clip not found.")
    return job_dir, data, ClipCandidate.model_validate(raw_clips[clip_index])


@app.post("/projects/{job_id}/clips/{clip_index}/generate-copy", response_model=ClipCopyResponse)
def generate_clip_copy(job_id: str, clip_index: int, request: ClipCopyGenerateRequest):
    job_dir, data, clip = _saved_clip(job_id, clip_index)
    transcript = _load_transcript(job_id)
    dialogue = dialogue_for_range(transcript, clip.start, clip.end)
    generated = generate_clip_copy_local(dialogue or clip.hook, request.style)

    clips = list(data.get("clips") or [])
    clips[clip_index] = {
        **clips[clip_index],
        "title": generated.title,
        "social_caption": generated.social_caption,
    }
    save_project(job_dir, {**data, "clips": clips})
    return ClipCopyResponse(
        clip_index=clip_index,
        title=generated.title,
        social_caption=generated.social_caption,
        style=generated.style,
    )


@app.patch("/projects/{job_id}/clips/{clip_index}/copy", response_model=ClipCopyResponse)
def update_clip_copy(job_id: str, clip_index: int, request: ClipCopyUpdateRequest):
    job_dir, data, _clip = _saved_clip(job_id, clip_index)
    title = request.title.strip()
    social_caption = request.social_caption.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title cannot be empty.")

    clips = list(data.get("clips") or [])
    clips[clip_index] = {
        **clips[clip_index],
        "title": title,
        "social_caption": social_caption,
    }
    save_project(job_dir, {**data, "clips": clips})
    return ClipCopyResponse(
        clip_index=clip_index,
        title=title,
        social_caption=social_caption,
        style="auto",
    )


@app.delete("/projects/{job_id}")
def delete_project(job_id: str):
    job_dir = _job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Saved project not found.")
    shutil.rmtree(job_dir)
    return {"ok": True, "job_id": job_id}


def _render_clip_core(request: RenderClipRequest, *, progress=None, cancel_event=None) -> RenderClipResponse:
    if request.end <= request.start:
        raise HTTPException(status_code=422, detail="Clip end must be greater than clip start.")

    def notify(value: int, stage: str, message: str) -> None:
        if progress is not None:
            progress(value, stage, message)

    source = _find_source(request.job_id)
    job_dir = _job_dir(request.job_id)
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    start_ms = round(request.start * 1000)
    end_ms = round(request.end * 1000)
    filename = f"clip_{start_ms}_{end_ms}.mp4"
    output = clips_dir / filename

    try:
        if output.exists() and output.stat().st_size > 0:
            notify(94, "Using cached clip", "This clip was already rendered, so Clip AI reused it.")
        else:
            notify(15, "Cutting clip", "Encoding the selected timestamp range…")
            cut_clip(str(source), str(output), request.start, request.end, cancel_event=cancel_event)
            notify(92, "Finalizing", "Making the MP4 browser-friendly…")
    except CancelledError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Clip render failed: {exc}") from exc

    project = load_project(job_dir)
    if project is not None:
        save_project(job_dir, project)

    media_url = f"/media/{request.job_id}/{filename}"
    return RenderClipResponse(
        job_id=request.job_id,
        filename=filename,
        start=round(request.start, 3),
        end=round(request.end, 3),
        duration=round(request.end - request.start, 3),
        media_url=media_url,
        download_url=f"{media_url}?download=true",
        kind="original",
    )


@app.post("/tasks/render-clip", response_model=TaskCreateResponse, status_code=202)
def start_render_clip_task(request: RenderClipRequest):
    def runner(task_id, cancel_event):
        return _render_clip_core(
            request,
            progress=lambda pct, stage, message: tasks.progress(task_id, pct, stage, message),
            cancel_event=cancel_event,
        )

    record = tasks.create("render", runner, job_id=request.job_id)
    return TaskCreateResponse(task_id=record["task_id"], job_id=request.job_id, status=record["status"])


@app.post("/render-clip", response_model=RenderClipResponse)
def render_clip(request: RenderClipRequest):
    return _render_clip_core(request)


def _render_short_core(request: RenderClipRequest, *, progress=None, cancel_event=None) -> RenderClipResponse:
    if request.end <= request.start:
        raise HTTPException(status_code=422, detail="Clip end must be greater than clip start.")

    def notify(value: int, stage: str, message: str) -> None:
        if progress is not None:
            progress(value, stage, message)

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()

    source = _find_source(request.job_id)
    transcript = _load_transcript(request.job_id)
    job_dir = _job_dir(request.job_id)
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    start_ms = round(request.start * 1000)
    end_ms = round(request.end * 1000)
    plan_filename = f"reframe_v19_1_{start_ms}_{end_ms}.json"
    plan_path = clips_dir / plan_filename

    try:
        check_cancel()
        if plan_path.exists():
            notify(22, "Loading framing", "Reusing the saved speaker-tracking plan…")
            reframe_plan = load_reframe_plan(plan_path)
        else:
            notify(8, "Scanning the scene", "Finding faces, motion and likely active speakers…")
            speech_intervals = [
                (segment.start, segment.end)
                for segment in transcript
                if segment.end >= request.start and segment.start <= request.end
            ]
            reframe_plan = plan_smart_reframe(
                str(source),
                request.start,
                request.end,
                target_width=720,
                target_height=1280,
                speech_intervals=speech_intervals,
            )
            save_reframe_plan(reframe_plan, plan_path)
        check_cancel()
        notify(34, "Choosing layout", "Resolving Auto framing, video size and caption style…")

        layout_mode = choose_layout(request.layout_mode, reframe_plan)
        caption_style = choose_caption_style(request.caption_style, layout_mode, reframe_plan)
        frame_size = choose_frame_size(request.frame_size, layout_mode, reframe_plan)
        caption_zone = choose_caption_zone(caption_style, layout_mode, reframe_plan)
        resolved_profile = auto_profile(layout_mode, caption_style, reframe_plan)

        offset_tag = f"p{request.caption_offset_ms}" if request.caption_offset_ms >= 0 else f"m{abs(request.caption_offset_ms)}"
        filename = f"short_v19_1_{request.platform}_{layout_mode}_{frame_size}_{caption_style}_{caption_zone}_{offset_tag}_{start_ms}_{end_ms}.mp4"
        subtitle_filename = f"captions_v19_1_{request.platform}_{layout_mode}_{frame_size}_{caption_style}_{caption_zone}_{offset_tag}_{start_ms}_{end_ms}.ass"
        output = clips_dir / filename
        subtitles = clips_dir / subtitle_filename

        notify(43, "Building captions", "Creating word-timed captions inside the video safe-zone…")
        _subtitle_path, word_timed = write_clip_ass(
            transcript,
            request.start,
            request.end,
            str(subtitles),
            caption_style=caption_style,
            layout_mode=layout_mode,
            frame_size=frame_size,
            width=720,
            height=1280,
            caption_offset_ms=request.caption_offset_ms,
            caption_zone=caption_zone,
            platform=request.platform,
        )
        check_cancel()

        if output.exists() and output.stat().st_size > 0:
            notify(89, "Using cached Short", "This exact Short already exists, so Clip AI skipped encoding.")
        else:
            notify(55, "Rendering Short", "Encoding the vertical video. This is usually the longest step…")
            try:
                render_adaptive_short(
                    str(source), str(output), str(subtitles), request.start, request.end,
                    reframe_plan=reframe_plan, layout_mode=layout_mode, frame_size=frame_size,
                    width=720, height=1280, cancel_event=cancel_event,
                )
            except CancelledError:
                raise
            except Exception:
                # Reliability fallback: if a dynamic tracking expression or unusual source
                # breaks FFmpeg, retry once with a safe centered path instead of failing outright.
                if reframe_plan.mode == "center":
                    raise
                check_cancel()
                notify(67, "Retrying safely", "The smart crop hit an encoding problem. Retrying with stable center framing…")
                duration = max(0.05, request.end - request.start)
                safe_plan = ReframePlan(
                    mode="center",
                    keyframes=[(0.0, 0.5), (duration, 0.5)],
                    source_width=reframe_plan.source_width,
                    source_height=reframe_plan.source_height,
                )
                render_adaptive_short(
                    str(source), str(output), str(subtitles), request.start, request.end,
                    reframe_plan=safe_plan, layout_mode=layout_mode, frame_size=frame_size,
                    width=720, height=1280, cancel_event=cancel_event,
                )
                reframe_plan = safe_plan

        check_cancel()
        cover_filename = f"cover_v19_1_{request.platform}_{layout_mode}_{frame_size}_{caption_style}_{start_ms}_{end_ms}.jpg"
        cover_path = clips_dir / cover_filename
        if not cover_path.exists() or cover_path.stat().st_size == 0:
            notify(92, "Creating cover", "Extracting a suggested cover frame…")
            extract_cover_frame(
                str(output), str(cover_path), max(0.15, (request.end - request.start) * 0.34),
                cancel_event=cancel_event,
            )
        notify(97, "Saving render", "Adding the finished Short to this project…")
    except CancelledError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Short render failed: {exc}") from exc

    project = load_project(job_dir)
    if project is not None:
        save_project(job_dir, project)

    media_url = f"/media/{request.job_id}/{filename}"
    return RenderClipResponse(
        job_id=request.job_id,
        filename=filename,
        start=round(request.start, 3),
        end=round(request.end, 3),
        duration=round(request.end - request.start, 3),
        media_url=media_url,
        download_url=f"{media_url}?download=true",
        kind="short",
        width=720,
        height=1280,
        framing_mode=reframe_plan.mode,
        layout_mode=layout_mode,
        caption_style=caption_style,
        frame_size=frame_size,
        tracking_samples=reframe_plan.sample_count,
        face_samples=reframe_plan.face_samples,
        motion_samples=reframe_plan.motion_samples,
        active_speaker_samples=reframe_plan.active_speaker_samples,
        active_speaker_switches=reframe_plan.active_speaker_switches,
        group_fallback_samples=reframe_plan.group_fallback_samples,
        caption_offset_ms=request.caption_offset_ms,
        word_timed_captions=word_timed,
        caption_zone=caption_zone,
        platform=request.platform,
        cover_url=f"/media/{request.job_id}/{cover_filename}",
        auto_profile=resolved_profile,
    )


@app.post("/tasks/render-short", response_model=TaskCreateResponse, status_code=202)
def start_render_short_task(request: RenderClipRequest):
    def runner(task_id, cancel_event):
        return _render_short_core(
            request,
            progress=lambda pct, stage, message: tasks.progress(task_id, pct, stage, message),
            cancel_event=cancel_event,
        )

    record = tasks.create("render", runner, job_id=request.job_id)
    return TaskCreateResponse(task_id=record["task_id"], job_id=request.job_id, status=record["status"])


@app.post("/render-short", response_model=RenderClipResponse)
def render_short(request: RenderClipRequest):
    return _render_short_core(request)


@app.get("/media/{job_id}/{filename}")
def media_file(
    job_id: str,
    filename: str,
    download: bool = Query(default=False),
    name: str | None = Query(default=None, max_length=140),
):
    suffix = Path(filename).suffix.lower()
    if not SAFE_FILENAME.fullmatch(filename) or suffix not in {".mp4", ".jpg", ".jpeg", ".png"}:
        raise HTTPException(status_code=400, detail="Invalid media filename.")

    path = _job_dir(job_id) / "clips" / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Rendered media not found.")

    media_types = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    response_name = None
    if download:
        response_name = safe_download_name(name, path.stem) if suffix == ".mp4" else (name or path.name)
    return FileResponse(path, media_type=media_types[suffix], filename=response_name)
