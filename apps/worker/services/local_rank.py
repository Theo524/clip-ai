import math
import re
from models import ClipCandidate, TranscriptSegment

HOOK_PHRASES = (
    "why ", "how ", "here's", "here is", "the biggest", "most people",
    "what if", "i learned", "i realised", "i realized", "you need",
    "never ", "always ", "the secret", "the problem", "the truth",
    "the mistake", "imagine", "nobody", "everyone", "the reason",
    "one thing", "this is", "you won't", "you will not",
)

FILLERS = {"um", "uh", "erm", "like", "basically", "literally"}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _first_sentence(text: str, max_chars: int = 180) -> str:
    text = _clean(text)
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentence = parts[0] if parts else text
    if len(sentence) > max_chars:
        sentence = sentence[: max_chars - 1].rstrip() + "…"
    return sentence


def _title_from_text(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9'’%$£€\- ]+", " ", _clean(text))
    words = text.split()
    title = " ".join(words[:10]).strip()
    if len(words) > 10:
        title += "…"
    return title or "Strong clip candidate"


def _candidate_score(text: str, duration: float) -> tuple[int, list[str]]:
    lower = text.lower()
    words = re.findall(r"\b[\w'’%-]+\b", lower)
    word_count = len(words)
    wpm = word_count / max(duration, 1) * 60

    score = 45.0
    reasons: list[str] = []

    # Duration: short-form sweet spot.
    if 28 <= duration <= 50:
        score += 14
        reasons.append("Good short-form length")
    elif 20 <= duration <= 60:
        score += 8
    else:
        score -= min(15, abs(duration - 40) * 0.5)

    # Strong opening / hook language.
    opening = lower[:180].lstrip('"“‘ ')
    if opening.endswith("?") or "?" in opening:
        score += 7
        reasons.append("Question-led hook")
    if any(opening.startswith(p) or f" {p}" in opening[:90] for p in HOOK_PHRASES):
        score += 12
        reasons.append("Strong opening language")

    # Specificity often helps clips stand alone.
    if re.search(r"\b\d+(?:\.\d+)?%?\b|[$£€]\s?\d", text):
        score += 7
        reasons.append("Specific detail or number")

    # Emotional / emphatic signals.
    emphasis_terms = (
        "crazy", "amazing", "terrible", "huge", "massive", "best", "worst",
        "mistake", "secret", "truth", "problem", "changed", "never", "always",
        "surprised", "shocked", "important", "dangerous", "love", "hate",
    )
    if any(term in lower for term in emphasis_terms):
        score += 7
        reasons.append("High-interest language")

    # Speaking density: penalise very sparse or frantic windows.
    if 105 <= wpm <= 200:
        score += 7
        reasons.append("Good speaking density")
    elif wpm < 70 or wpm > 240:
        score -= 8

    # Completeness: punctuation near the end suggests a clean payoff.
    if _clean(text).endswith((".", "!", "?")):
        score += 5
        reasons.append("Clean ending")

    filler_count = sum(1 for word in words if word in FILLERS)
    if word_count and filler_count / word_count > 0.08:
        score -= 6

    # Reward enough substance, but not rambling.
    if 55 <= word_count <= 170:
        score += 5
    elif word_count < 30:
        score -= 10

    # Keep local scores conservative so API scoring can be meaningfully better later.
    return max(1, min(96, round(score))), reasons[:4]


def _overlap_ratio(a: ClipCandidate, b: ClipCandidate) -> float:
    intersection = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    if intersection <= 0:
        return 0.0
    return intersection / max(1.0, min(a.end - a.start, b.end - b.start))


def rank_clip_candidates_local(
    segments: list[TranscriptSegment],
    max_clips: int,
) -> list[ClipCandidate]:
    """Cheap local fallback for development.

    It builds 20–60 second transcript windows, scores hook/completeness/specificity,
    then removes heavily overlapping candidates. It is intentionally simpler than
    LLM ranking but is enough to test the full product pipeline with zero API cost.
    """
    if not segments:
        return []

    candidates: list[ClipCandidate] = []
    n = len(segments)

    for start_index in range(n):
        start = segments[start_index].start
        pieces: list[str] = []

        for end_index in range(start_index, min(n, start_index + 24)):
            seg = segments[end_index]
            pieces.append(seg.text)
            duration = seg.end - start

            if duration < 20:
                continue
            if duration > 60:
                break

            # Evaluate a few natural endpoints rather than every tiny extension.
            ends_clean = _clean(seg.text).endswith((".", "!", "?"))
            near_target = duration >= 32
            if not (ends_clean or near_target):
                continue

            text = _clean(" ".join(pieces))
            score, reasons = _candidate_score(text, duration)
            candidates.append(
                ClipCandidate(
                    start=round(start, 2),
                    end=round(seg.end, 2),
                    title=_title_from_text(text),
                    hook=_first_sentence(text),
                    score=score,
                    reasons=reasons or ["Complete self-contained moment"],
                )
            )

    candidates.sort(key=lambda c: (c.score, -(c.end - c.start)), reverse=True)

    selected: list[ClipCandidate] = []
    for candidate in candidates:
        if any(_overlap_ratio(candidate, existing) > 0.55 for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_clips:
            break

    # Very short transcripts can fail the 20-second threshold. Return one usable range.
    if not selected and segments:
        text = _clean(" ".join(s.text for s in segments))
        duration = segments[-1].end - segments[0].start
        score, reasons = _candidate_score(text, duration)
        selected.append(
            ClipCandidate(
                start=round(segments[0].start, 2),
                end=round(segments[-1].end, 2),
                title=_title_from_text(text),
                hook=_first_sentence(text),
                score=score,
                reasons=reasons or ["Best available local candidate"],
            )
        )

    return selected[:max_clips]
