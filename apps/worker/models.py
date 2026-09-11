from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class AnalyzeRequest(BaseModel):
    source_url: HttpUrl
    local_media_path: str | None = None
    max_clips: int = Field(default=6, ge=1, le=12)


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class ClipCandidate(BaseModel):
    start: float
    end: float
    title: str
    hook: str
    score: int = Field(ge=0, le=100)
    reasons: list[str]


class AnalyzeResponse(BaseModel):
    source_url: str
    mock: bool
    clips: list[ClipCandidate]
    job_id: str | None = None


class RenderClipRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=100)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    layout_mode: Literal["auto", "fill", "focus", "backdrop", "preserve"] = "auto"
    caption_style: Literal["auto", "viral", "cinematic", "clean", "meme"] = "auto"
    frame_size: Literal["compact", "balanced", "immersive"] = "balanced"


class RenderClipResponse(BaseModel):
    job_id: str
    filename: str
    start: float
    end: float
    duration: float
    media_url: str
    download_url: str
    kind: str = "original"
    width: int | None = None
    height: int | None = None
    framing_mode: str | None = None
    layout_mode: str | None = None
    caption_style: str | None = None
    frame_size: str | None = None
    tracking_samples: int | None = None
    face_samples: int | None = None
    motion_samples: int | None = None
