from typing import Literal

ContentType = Literal["auto", "podcast", "anime", "film-tv", "documentary", "meme-comedy", "gameplay", "other"]
ContentStructure = Literal["auto", "single-story", "compilation", "conversation"]

from pydantic import BaseModel, Field, HttpUrl


class AnalyzeRequest(BaseModel):
    source_url: HttpUrl
    local_media_path: str | None = None
    max_clips: int = Field(default=6, ge=1, le=12)
    processing_profile: Literal["low-memory", "balanced", "fast"] = "balanced"
    content_type: ContentType = "auto"
    content_structure: ContentStructure = "auto"
    subject_hint: str | None = Field(default=None, max_length=160)


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
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    editor_note: str | None = None
    context: dict = Field(default_factory=dict)


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
    frame_size: Literal["auto", "compact", "balanced", "immersive"] = "auto"
    caption_offset_ms: int = Field(default=0, ge=-1000, le=1000)
    platform: Literal["auto", "shorts", "tiktok", "reels"] = "auto"
    cover_offset_seconds: float | None = Field(default=None, ge=0, le=180)


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
    active_speaker_samples: int | None = None
    active_speaker_switches: int | None = None
    group_fallback_samples: int | None = None
    caption_offset_ms: int | None = None
    word_timed_captions: bool | None = None
    caption_zone: str | None = None
    platform: str | None = None
    cover_url: str | None = None
    auto_profile: str | None = None


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
    status: str = "ready"
    processing_profile: str = "balanced"
    content_type: str = "auto"
    resolved_content_type: str = "other"
    content_structure: str = "auto"
    resolved_content_structure: str = "single-story"
    subject_hint: str | None = None
    context_confidence: float = 0.0


class ProjectDetail(ProjectSummary):
    clips: list[ClipCandidate] = Field(default_factory=list)
    renders: list[SavedRender] = Field(default_factory=list)


class TaskCreateResponse(BaseModel):
    task_id: str
    job_id: str | None = None
    status: str = "queued"


class TaskStatusResponse(BaseModel):
    task_id: str
    kind: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    stage: str
    progress: int = Field(ge=0, le=100)
    message: str | None = None
    job_id: str | None = None
    result: dict | list | str | int | float | bool | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    recoverable: bool = False



class ClipTimingUpdateRequest(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class TranscriptEditRequest(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(max_length=5000)


class TranscriptRangeResponse(BaseModel):
    start: float
    end: float
    text: str
    segment_count: int


class CoverRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    at_seconds: float = Field(ge=0, le=180)


class SystemCheck(BaseModel):
    id: str
    label: str
    ok: bool
    detail: str
    severity: Literal["required", "warning", "info"] = "required"


class SystemPreflightResponse(BaseModel):
    version: str
    release: str
    ready: bool
    checks: list[SystemCheck] = Field(default_factory=list)
    transcription_backend: str
    ranking_backend: str
    local_whisper_model: str
    work_dir: str
    project_count: int = 0
    project_storage_bytes: int = 0
    disk_free_bytes: int = 0
    disk_total_bytes: int = 0
    privacy_note: str


class CleanupResponse(BaseModel):
    removed_files: int = 0
    removed_bytes: int = 0
    startup_cleanup: int = 0

