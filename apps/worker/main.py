from pathlib import Path
from urllib.parse import urlparse
import uuid

from fastapi import FastAPI, HTTPException

from models import AnalyzeRequest, AnalyzeResponse
from settings import settings
from services.media import extract_audio
from services.mock import mock_clips

app = FastAPI(title="Clip AI Worker", version="0.1.0")


def is_youtube_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


@app.get("/health")
def health():
    return {"ok": True, "mock_mode": settings.mock_mode}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    source_url = str(request.source_url)
    if not is_youtube_url(source_url):
        raise HTTPException(status_code=400, detail="For Milestone 1, enter a YouTube URL.")

    if settings.mock_mode:
        return AnalyzeResponse(source_url=source_url, mock=True, clips=mock_clips(request.max_clips))

    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is required when MOCK_MODE=false.")

    if not request.local_media_path:
        raise HTTPException(
            status_code=422,
            detail=(
                "The URL UI is wired, but real media ingestion is intentionally behind an authorised-import boundary. "
                "Provide local_media_path for now; the next milestone connects owned/authorised YouTube media or upload."
            ),
        )

    try:
        from services.rank import rank_clip_candidates
        from services.transcribe import transcribe_with_timestamps

        job_dir = Path(settings.work_dir) / str(uuid.uuid4())
        job_dir.mkdir(parents=True, exist_ok=True)
        audio_path = extract_audio(request.local_media_path, str(job_dir / "audio.mp3"))
        segments = transcribe_with_timestamps(audio_path, settings.openai_api_key)
        if not segments:
            raise RuntimeError("No transcript segments were produced.")
        clips = rank_clip_candidates(
            segments=segments,
            api_key=settings.openai_api_key,
            model=settings.openai_rank_model,
            max_clips=request.max_clips,
        )
        return AnalyzeResponse(source_url=source_url, mock=False, clips=clips)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc
