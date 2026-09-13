from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from models import TranscriptSegment

CONTENT_TYPES = {
    "auto",
    "podcast",
    "anime",
    "film-tv",
    "documentary",
    "meme-comedy",
    "gameplay",
    "other",
}

CONTENT_STRUCTURES = {"auto", "single-story", "compilation", "conversation"}


@dataclass(frozen=True)
class ContentContext:
    requested_type: str
    resolved_type: str
    requested_structure: str
    resolved_structure: str
    subject_hint: str | None
    confidence: float
    signals: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "requested_type": self.requested_type,
            "resolved_type": self.resolved_type,
            "requested_structure": self.requested_structure,
            "resolved_structure": self.resolved_structure,
            "subject_hint": self.subject_hint,
            "confidence": round(self.confidence, 3),
            "signals": list(self.signals),
        }


def normalize_content_type(value: str | None) -> str:
    value = (value or "auto").strip().lower()
    return value if value in CONTENT_TYPES else "auto"


def normalize_content_structure(value: str | None) -> str:
    value = (value or "auto").strip().lower()
    return value if value in CONTENT_STRUCTURES else "auto"


def normalize_subject_hint(value: str | None) -> str | None:
    if not value:
        return None
    clean = re.sub(r"\s+", " ", value).strip()
    return clean[:160] or None


def _text(segments: Iterable[TranscriptSegment]) -> str:
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip()).lower()


def _detect_type(segments: list[TranscriptSegment], project_title: str | None, subject_hint: str | None) -> tuple[str, float, list[str]]:
    # M1 intentionally stays conservative. Later milestones can add richer visual/audio
    # classification without changing the persisted context contract introduced here.
    title_text = f"{project_title or ''} {subject_hint or ''}".lower()
    transcript = _text(segments[: min(len(segments), 180)])
    combined = f"{title_text} {transcript[:18000]}"

    scores: dict[str, float] = {
        "podcast": 0.0,
        "anime": 0.0,
        "film-tv": 0.0,
        "documentary": 0.0,
        "meme-comedy": 0.0,
        "gameplay": 0.0,
    }
    signals: list[str] = []

    keyword_groups = {
        "podcast": ("podcast", "episode", "welcome back", "our guest", "on the show", "interview"),
        "anime": ("anime", "manga", "episode ", "season ", "subbed", "dubbed"),
        "film-tv": ("movie", "film", "tv series", "television", "scene", "episode "),
        "documentary": ("documentary", "species", "habitat", "scientists", "researchers", "in the wild", "history of", "million years"),
        "meme-comedy": ("funny", "meme", "comedy", "joke", "prank", "laugh", "roast"),
        "gameplay": ("gameplay", "let's play", "level", "boss fight", "respawn", "ranked", "match", "quest"),
    }

    for kind, keywords in keyword_groups.items():
        for keyword in keywords:
            if keyword in title_text:
                scores[kind] += 2.8
                signals.append(f"title/subject mentions {keyword.strip()}")
            if keyword in transcript:
                scores[kind] += 0.8

    # Conversational phrasing is a weak podcast/interview signal, never enough alone.
    question_count = transcript.count("?")
    first_person = sum(transcript.count(token) for token in (" i ", " we ", " you "))
    if len(transcript) > 1000 and question_count >= 4 and first_person >= 18:
        scores["podcast"] += 1.2
        signals.append("dialogue-heavy transcript")

    best_kind, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score < 2.4:
        return "other", 0.35, signals[:4]

    second = sorted(scores.values(), reverse=True)[1]
    margin = max(0.0, best_score - second)
    confidence = min(0.92, 0.5 + min(best_score, 6.0) * 0.055 + margin * 0.04)
    return best_kind, confidence, signals[:4]


def _topic_tokens(text: str) -> set[str]:
    stop = {
        "this", "that", "with", "from", "have", "your", "they", "there", "what", "when", "were", "then",
        "just", "like", "about", "into", "would", "could", "really", "because", "which", "their", "them",
        "been", "some", "more", "very", "only", "also", "here", "where", "will", "than", "does", "dont",
    }
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) >= 4 and w not in stop}


def _detect_structure(segments: list[TranscriptSegment], resolved_type: str) -> tuple[str, float, list[str]]:
    if not segments:
        return "single-story", 0.35, []

    duration = max(0.0, segments[-1].end - segments[0].start)
    long_gaps = [max(0.0, segments[i].start - segments[i - 1].end) for i in range(1, len(segments))]
    hard_breaks = sum(1 for gap in long_gaps if gap >= 2.2)
    very_hard_breaks = sum(1 for gap in long_gaps if gap >= 4.0)

    # Compare coarse transcript blocks. Repeated low overlap plus hard pauses is a useful
    # compilation hint, while staying intentionally conservative in M1.
    block_size = 8
    blocks: list[set[str]] = []
    for i in range(0, len(segments), block_size):
        block = " ".join(s.text for s in segments[i : i + block_size])
        tokens = _topic_tokens(block)
        if tokens:
            blocks.append(tokens)
    low_overlap = 0
    comparisons = 0
    for left, right in zip(blocks, blocks[1:]):
        union = left | right
        if not union:
            continue
        comparisons += 1
        jaccard = len(left & right) / len(union)
        if jaccard < 0.08:
            low_overlap += 1
    shift_ratio = low_overlap / comparisons if comparisons else 0.0

    transcript = _text(segments)
    compilation_cues = sum(transcript.count(cue) for cue in ("next clip", "next one", "number one", "number two", "compilation", "top ten", "top 10"))

    compilation_score = 0.0
    signals: list[str] = []
    if duration >= 150 and hard_breaks >= 3:
        compilation_score += 1.5
        signals.append("several long transcript breaks")
    if very_hard_breaks >= 2:
        compilation_score += 1.2
        signals.append("multiple major pauses")
    if shift_ratio >= 0.58 and comparisons >= 4:
        compilation_score += 1.5
        signals.append("frequent local topic changes")
    if compilation_cues:
        compilation_score += min(2.5, compilation_cues * 0.9)
        signals.append("compilation-style wording")

    if compilation_score >= 2.6:
        return "compilation", min(0.9, 0.55 + compilation_score * 0.08), signals[:4]

    if resolved_type == "podcast":
        return "conversation", 0.72, ["podcast/interview content"]

    return "single-story", 0.62 if duration >= 60 else 0.52, signals[:4]


def resolve_content_context(
    segments: list[TranscriptSegment],
    *,
    requested_type: str | None = "auto",
    requested_structure: str | None = "auto",
    subject_hint: str | None = None,
    project_title: str | None = None,
) -> ContentContext:
    req_type = normalize_content_type(requested_type)
    req_structure = normalize_content_structure(requested_structure)
    hint = normalize_subject_hint(subject_hint)

    detected_type, type_confidence, type_signals = _detect_type(segments, project_title, hint)
    resolved_type = detected_type if req_type == "auto" else req_type
    if req_type != "auto":
        type_confidence = 1.0
        type_signals = ["user-selected content type"]

    detected_structure, structure_confidence, structure_signals = _detect_structure(segments, resolved_type)
    resolved_structure = detected_structure if req_structure == "auto" else req_structure
    if req_structure != "auto":
        structure_confidence = 1.0
        structure_signals = ["user-selected content structure"]

    signals = tuple(dict.fromkeys(type_signals + structure_signals))[:6]
    return ContentContext(
        requested_type=req_type,
        resolved_type=resolved_type,
        requested_structure=req_structure,
        resolved_structure=resolved_structure,
        subject_hint=hint,
        confidence=min(type_confidence, structure_confidence),
        signals=signals,
    )


def candidate_context(context: ContentContext, start: float, end: float, scene_start: float | None = None, scene_end: float | None = None) -> dict:
    # Store a local-context envelope now so M2 can change ranking/boundaries without
    # another project-schema migration. The range deliberately stays local for
    # compilation sources.
    pad_before = 18.0 if context.resolved_structure == "compilation" else 30.0
    pad_after = 24.0 if context.resolved_structure == "compilation" else 36.0
    return {
        "content_type": context.resolved_type,
        "content_structure": context.resolved_structure,
        "subject_hint": context.subject_hint,
        "local_context_start": round(max(0.0, start - pad_before, scene_start if scene_start is not None else 0.0), 3),
        "local_context_end": round(min(end + pad_after, scene_end if scene_end is not None else end + pad_after), 3),
        "moment_type": "unknown",
    }
