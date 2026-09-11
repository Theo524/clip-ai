from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class AnalyzeRequest(BaseModel):
    source_url: HttpUrl
    local_media_path: str | None = None
    max_clips: int = Field(default=6, ge=1, le=12)


class YouTubeInfoResponse(BaseModel):
    source_url: str
    title: str
    author_name: str | None = None
    thumbnail_url: str | None = None
    provider_name: str = "YouTube"


class TranscriptWord(BaseModel):
    start: float
    end: float
    text: str
    probability: float | None = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    words: list[TranscriptWord] = Field(default_factory=list)


class ClipCandidate(BaseModel):
    start: float
    end: float
    title: str
    hook: str
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    social_caption: str | None = None


class ClipCopyGenerateRequest(BaseModel):
    style: Literal["auto", "viral", "clean", "cinematic"] = "auto"


class ClipCopyUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    social_caption: str = Field(default="", max_length=500)


class ClipCopyResponse(BaseModel):
    clip_index: int
    title: str
    social_caption: str
    style: Literal["auto", "viral", "clean", "cinematic"] = "auto"


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
    caption_offset_ms: int = Field(default=0, ge=-1000, le=1000)
    platform: Literal["auto", "shorts", "tiktok", "reels"] = "auto"


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
    caption_offset_ms: int | None = None
    word_timed_captions: bool | None = None
    caption_zone: str | None = None
    platform: str | None = None
    cover_url: str | None = None


class SavedRender(BaseModel):
    filename: str
    kind: Literal["short", "original"]
    media_url: str
    download_url: str
    size_bytes: int = 0
    created_at: str


class ProjectSummary(BaseModel):
    job_id: str
    title: str
    source_type: Literal["upload", "youtube"]
    source_url: str | None = None
    author_name: str | None = None
    thumbnail_url: str | None = None
    created_at: str
    updated_at: str
    clip_count: int = 0
    render_count: int = 0
    storage_bytes: int = 0


class ProjectDetail(ProjectSummary):
    clips: list[ClipCandidate] = Field(default_factory=list)
    renders: list[SavedRender] = Field(default_factory=list)
