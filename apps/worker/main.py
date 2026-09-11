from pathlib import Path
import json
from urllib.parse import urlparse
import re
import shutil
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models import AnalyzeRequest, AnalyzeResponse, RenderClipRequest, RenderClipResponse, TranscriptSegment
from settings import settings
from services.media import cut_clip, extract_audio_chunks, render_adaptive_short
from services.captions import write_clip_ass
from services.mock import mock_clips
from services.reframe import load_reframe_plan, plan_smart_reframe, save_reframe_plan
from services.layouts import choose_caption_style, choose_layout, normalize_frame_size

app = FastAPI(title="Clip AI Worker", version="0.7.0")
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


def is_youtube_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


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


def analyze_local_media(
    media_path: str,
    source_label: str,
    max_clips: int,
    *,
    job_id: str | None = None,
) -> AnalyzeResponse:
    try:
        resolved_job_id = job_id or str(uuid.uuid4())
        job_dir = _job_dir(resolved_job_id)
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

        transcript_path = job_dir / "transcript.json"
        transcript_path.write_text(
            json.dumps([segment.model_dump() for segment in segments], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        clips = _rank_segments(segments, max_clips=max_clips)
        return AnalyzeResponse(
            source_url=source_label,
            mock=False,
            clips=clips,
            job_id=resolved_job_id,
        )
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

    return analyze_local_media(str(saved_path), filename, max_clips, job_id=job_id)


@app.post("/render-clip", response_model=RenderClipResponse)
def render_clip(request: RenderClipRequest):
    if request.end <= request.start:
        raise HTTPException(status_code=422, detail="Clip end must be greater than clip start.")

    source = _find_source(request.job_id)
    job_dir = _job_dir(request.job_id)
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    start_ms = round(request.start * 1000)
    end_ms = round(request.end * 1000)
    filename = f"clip_{start_ms}_{end_ms}.mp4"
    output = clips_dir / filename

    try:
        if not output.exists() or output.stat().st_size == 0:
            cut_clip(str(source), str(output), request.start, request.end)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Clip render failed: {exc}") from exc

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


@app.post("/render-short", response_model=RenderClipResponse)
def render_short(request: RenderClipRequest):
    if request.end <= request.start:
        raise HTTPException(status_code=422, detail="Clip end must be greater than clip start.")

    source = _find_source(request.job_id)
    transcript = _load_transcript(request.job_id)
    job_dir = _job_dir(request.job_id)
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    start_ms = round(request.start * 1000)
    end_ms = round(request.end * 1000)
    plan_filename = f"reframe_{start_ms}_{end_ms}.json"
    plan_path = clips_dir / plan_filename

    try:
        if plan_path.exists():
            reframe_plan = load_reframe_plan(plan_path)
        else:
            reframe_plan = plan_smart_reframe(
                str(source),
                request.start,
                request.end,
                target_width=720,
                target_height=1280,
            )
            save_reframe_plan(reframe_plan, plan_path)

        layout_mode = choose_layout(request.layout_mode, reframe_plan)
        caption_style = choose_caption_style(request.caption_style, layout_mode, reframe_plan)
        frame_size = normalize_frame_size(request.frame_size)

        filename = f"short_{layout_mode}_{frame_size}_{caption_style}_{start_ms}_{end_ms}.mp4"
        subtitle_filename = f"captions_{layout_mode}_{frame_size}_{caption_style}_{start_ms}_{end_ms}.ass"
        output = clips_dir / filename
        subtitles = clips_dir / subtitle_filename

        write_clip_ass(
            transcript,
            request.start,
            request.end,
            str(subtitles),
            caption_style=caption_style,
            layout_mode=layout_mode,
            frame_size=frame_size,
            width=720,
            height=1280,
        )

        if not output.exists() or output.stat().st_size == 0:
            render_adaptive_short(
                str(source),
                str(output),
                str(subtitles),
                request.start,
                request.end,
                reframe_plan=reframe_plan,
                layout_mode=layout_mode,
                frame_size=frame_size,
                width=720,
                height=1280,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Short render failed: {exc}") from exc

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
    )


@app.get("/media/{job_id}/{filename}")
def media_file(
    job_id: str,
    filename: str,
    download: bool = Query(default=False),
):
    if not SAFE_FILENAME.fullmatch(filename) or not filename.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Invalid media filename.")

    path = _job_dir(job_id) / "clips" / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Rendered clip not found.")

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename if download else None,
    )
