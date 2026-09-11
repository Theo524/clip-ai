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
