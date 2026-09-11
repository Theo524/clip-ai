from pathlib import Path
import json
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import re
import shutil
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models import AnalyzeRequest, AnalyzeResponse, ClipCandidate, ClipCopyGenerateRequest, ClipCopyResponse, ClipCopyUpdateRequest, ProjectDetail, ProjectSummary, RenderClipRequest, RenderClipResponse, TranscriptSegment, YouTubeInfoResponse
from settings import settings
from services.media import cut_clip, extract_audio_chunks, extract_cover_frame, render_adaptive_short
from services.captions import write_clip_ass
from services.mock import mock_clips
from services.reframe import load_reframe_plan, plan_smart_reframe, save_reframe_plan
from services.layouts import auto_profile, choose_caption_style, choose_caption_zone, choose_frame_size, choose_layout
from services.projects import directory_size, load_project, rendered_media, save_project
from services.copywriter import dialogue_for_range, generate_clip_copy_local

app = FastAPI(title="Clip AI Worker", version="0.17.0")
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
    request = Request(endpoint, headers={"User-Agent": "ClipAI/0.17"})
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
    project_title: str | None = None,
    source_type: str = "upload",
    author_name: str | None = None,
    thumbnail_url: str | None = None,
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
        # Copy is generated from the exact dialogue inside each selected clip. This keeps
        # titles useful without inventing facts that were not spoken in the source.
        for clip in clips:
            dialogue = dialogue_for_range(segments, clip.start, clip.end)
            generated = generate_clip_copy_local(dialogue or clip.hook, "auto")
            if settings.ranking_backend.lower().strip() == "local" or not clip.title.strip():
                clip.title = generated.title
            clip.social_caption = generated.social_caption

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
        "word_timestamps": True,
    }


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
    plan_filename = f"reframe_v17_{start_ms}_{end_ms}.json"
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
        frame_size = choose_frame_size(request.frame_size, layout_mode, reframe_plan)
        caption_zone = choose_caption_zone(caption_style, layout_mode, reframe_plan)
        resolved_profile = auto_profile(layout_mode, caption_style, reframe_plan)

        offset_tag = f"p{request.caption_offset_ms}" if request.caption_offset_ms >= 0 else f"m{abs(request.caption_offset_ms)}"
        filename = f"short_v17_{request.platform}_{layout_mode}_{frame_size}_{caption_style}_{caption_zone}_{offset_tag}_{start_ms}_{end_ms}.mp4"
        subtitle_filename = f"captions_v17_{request.platform}_{layout_mode}_{frame_size}_{caption_style}_{caption_zone}_{offset_tag}_{start_ms}_{end_ms}.ass"
        output = clips_dir / filename
        subtitles = clips_dir / subtitle_filename

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

        cover_filename = f"cover_v17_{request.platform}_{layout_mode}_{frame_size}_{caption_style}_{start_ms}_{end_ms}.jpg"
        cover_path = clips_dir / cover_filename
        if not cover_path.exists() or cover_path.stat().st_size == 0:
            # Around one third into the clip usually avoids cold opens while still
            # reflecting the selected moment. The user can later choose covers manually.
            extract_cover_frame(str(output), str(cover_path), max(0.15, (request.end - request.start) * 0.34))
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
        caption_offset_ms=request.caption_offset_ms,
        word_timed_captions=word_timed,
        caption_zone=caption_zone,
        platform=request.platform,
        cover_url=f"/media/{request.job_id}/{cover_filename}",
        auto_profile=resolved_profile,
    )


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
