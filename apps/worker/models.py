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


class RenderClipResponse(BaseModel):
    job_id: str
    filename: str
    start: float
    end: float
    duration: float
    media_url: str
    download_url: str
