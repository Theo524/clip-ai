from pathlib import Path
from urllib.parse import urlparse
import shutil
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models import AnalyzeRequest, AnalyzeResponse
from settings import settings
from services.media import extract_audio_chunks
from services.mock import mock_clips

app = FastAPI(title="Clip AI Worker", version="0.2.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def is_youtube_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def _transcribe_chunk(chunk_path: str, offset_seconds: float):
    backend = settings.transcription_backend.lower().strip()

    if backend == "local":
        from services.transcribe import transcribe_local_with_timestamps
        return transcribe_local_with_timestamps(
            chunk_path,
            model_name=settings.local_whisper_model,
            device=settings.local_whisper_device,
            compute_type=settings.local_whisper_compute_type,
            offset_seconds=offset_seconds,
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


def analyze_local_media(media_path: str, source_label: str, max_clips: int) -> AnalyzeResponse:
    try:
        job_dir = Path(settings.work_dir) / str(uuid.uuid4())
        job_dir.mkdir(parents=True, exist_ok=True)
        audio_dir = job_dir / "audio"
        chunks = extract_audio_chunks(
            media_path,
            str(audio_dir),
            chunk_seconds=settings.audio_chunk_seconds,
        )

        segments = []
        for index, chunk_path in enumerate(chunks):
            segments.extend(
                _transcribe_chunk(
                    chunk_path,
                    offset_seconds=index * settings.audio_chunk_seconds,
                )
            )

        if not segments:
            raise RuntimeError("No transcript segments were produced.")

        clips = _rank_segments(segments, max_clips=max_clips)
        return AnalyzeResponse(source_url=source_label, mock=False, clips=clips)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


@app.get("/health")
def health():
    return {
        "ok": True,
        "mock_mode": settings.mock_mode,
        "transcription_backend": settings.transcription_backend,
        "ranking_backend": settings.ranking_backend,
        "local_whisper_model": settings.local_whisper_model,
        "api_key_configured": bool(settings.openai_api_key),
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
    }


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    source_url = str(request.source_url)
    if not is_youtube_url(source_url):
        raise HTTPException(status_code=400, detail="Enter a YouTube URL.")

    if settings.mock_mode:
        return AnalyzeResponse(source_url=source_url, mock=True, clips=mock_clips(request.max_clips))

    if not request.local_media_path:
        raise HTTPException(
            status_code=422,
            detail="Direct YouTube ingestion is not connected yet. Upload an authorised video file for real analysis.",
        )

    return analyze_local_media(request.local_media_path, source_url, request.max_clips)


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

    job_dir = Path(settings.work_dir) / str(uuid.uuid4())
    job_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"source{suffix}"
    saved_path = job_dir / safe_name

    try:
        with saved_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
    finally:
        await file.close()

    return analyze_local_media(str(saved_path), filename, max_clips)
