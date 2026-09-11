import re
from models import ClipCandidate, TranscriptSegment
from services.copywriter import generate_clip_copy_local

HOOK_PHRASES = (
    "why ", "how ", "here's", "here is", "the biggest", "most people",
    "what if", "i learned", "i realised", "i realized", "you need",
    "never ", "always ", "the secret", "the problem", "the truth",
    "the mistake", "imagine", "nobody", "everyone", "the reason",
    "one thing", "this is", "you won't", "you will not", "i was wrong",
    "the moment", "the weird thing", "the crazy thing", "turns out",
)

DEPENDENT_STARTS = (
    "and ", "but ", "so ", "because ", "then ", "also ", "which ",
    "that ", "anyway ", "like ", "well ", "yeah ", "yes ", "no ",
    "he ", "she ", "they ", "it ", "them ", "his ", "her ", "their ",
)

PAYOFF_PHRASES = (
    "that's why", "that is why", "so now", "and that's", "which means",
    "the result", "the lesson", "i learned", "i realised", "i realized",
    "turns out", "in the end", "eventually", "from then on", "ever since",
    "the point is", "what matters", "the answer", "the reason is",
)

PIVOT_PHRASES = (
    "but ", "however", "until ", "then ", "instead", "except", "yet ",
    "because ", "so ", "which is why", "turns out", "the problem was",
)

INTEREST_TERMS = (
    "crazy", "amazing", "terrible", "huge", "massive", "best", "worst",
    "mistake", "secret", "truth", "problem", "changed", "never", "always",
    "surprised", "shocked", "important", "dangerous", "love", "hate",
    "failed", "failure", "million", "billion", "money", "risk", "wrong",
)

FILLERS = {
    "um", "uh", "erm", "hmm", "like", "basically", "literally", "actually",
    "you know", "sort of", "kind of",
}

TRAILING_DEPENDENCIES = (
    "and", "but", "because", "so", "then", "which", "that", "if", "when",
    "while", "although", "or",
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"\b[\w'’%-]+\b", text.lower())


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


def _starts_clean(text: str) -> bool:
    opening = _clean(text).lower().lstrip('"“‘')
    if not opening:
        return False
    first_words = _words(opening[:80])
    first = first_words[0] if first_words else ""
    dependent_first_words = {prefix.strip() for prefix in DEPENDENT_STARTS}
    if first in dependent_first_words:
        # A dependent word can still be an intentional hook, e.g. "So here's...".
        if any(hook in opening[:90] for hook in HOOK_PHRASES):
            return True
        return False
    return True


def _ends_clean(text: str) -> bool:
    cleaned = _clean(text)
    if not cleaned:
        return False
    last_word = _words(cleaned[-80:])[-1:] or [""]
    if last_word[0] in TRAILING_DEPENDENCIES:
        return False
    return cleaned.endswith((".", "!", "?", "…"))


def _gap_before(segments: list[TranscriptSegment], index: int) -> float:
    if index <= 0:
        return 10.0
    return max(0.0, segments[index].start - segments[index - 1].end)


def _gap_after(segments: list[TranscriptSegment], index: int) -> float:
    if index >= len(segments) - 1:
        return 10.0
    return max(0.0, segments[index + 1].start - segments[index].end)


def _candidate_score(
    text: str,
    duration: float,
    start_text: str,
    end_text: str,
    gap_before: float,
    gap_after: float,
) -> tuple[int, list[str]]:
    lower = text.lower()
    words = _words(text)
    word_count = len(words)
    wpm = word_count / max(duration, 1.0) * 60
    opening = _clean(start_text).lower().lstrip('"“‘')
    ending = _clean(end_text).lower()

    score = 36.0
    reasons: list[tuple[int, str]] = []

    # Short-form duration preference. 24-48s is the strongest local sweet spot,
    # while 18-60s remains usable for a complete idea.
    if 24 <= duration <= 48:
        score += 15
        reasons.append((15, "Strong Shorts length"))
    elif 18 <= duration <= 60:
        score += 8
        reasons.append((8, "Usable short-form length"))
    else:
        score -= min(18, abs(duration - 36) * 0.65)

    # Opening quality matters a lot. We want a clip that can stand on its own.
    clean_start = _starts_clean(start_text)
    if clean_start:
        score += 8
        reasons.append((8, "Clean standalone opening"))
    else:
        score -= 15

    if any(opening.startswith(p) or p in opening[:110] for p in HOOK_PHRASES):
        score += 14
        reasons.append((14, "Strong opening hook"))
    if "?" in _clean(start_text)[:180]:
        score += 8
        reasons.append((8, "Question-led hook"))
    if re.search(r"\b\d+(?:\.\d+)?%?\b|[$£€]\s?\d", _clean(start_text)[:220]):
        score += 5
        reasons.append((5, "Specific opening detail"))

    # Natural speech boundaries reduce awkward cuts.
    if gap_before >= 0.35:
        score += 4
        reasons.append((4, "Natural start boundary"))
    if _ends_clean(end_text):
        score += 8
        reasons.append((8, "Clean ending"))
    else:
        score -= 12
    if gap_after >= 0.35:
        score += 4
        reasons.append((4, "Natural end boundary"))

    # Arc/payoff: reward clips that move somewhere rather than being one flat excerpt.
    latter_half = lower[len(lower) // 2 :]
    ending_lower = _clean(end_text).lower()
    payoff_positions = [lower.rfind(cue) for cue in PAYOFF_PHRASES if cue in lower]
    last_payoff = max(payoff_positions) if payoff_positions else -1
    payoff_in_ending = any(cue in ending_lower for cue in PAYOFF_PHRASES)
    if payoff_in_ending:
        score += 13
        reasons.append((13, "Ends on a clear payoff"))
    elif any(cue in latter_half for cue in PAYOFF_PHRASES):
        score += 7
        reasons.append((7, "Contains a payoff or takeaway"))
        # If the clip already lands its point and then keeps rambling, prefer the
        # tighter endpoint. This is one of the biggest differences between a
        # useful clip and a merely interesting transcript window.
        if last_payoff >= 0:
            trailing_fraction = (len(lower) - last_payoff) / max(len(lower), 1)
            if trailing_fraction > 0.20:
                score -= 18
    if not _starts_clean(end_text) and not payoff_in_ending:
        score -= 10
    if any(cue in lower for cue in PIVOT_PHRASES):
        score += 6
        reasons.append((6, "Has a story/idea turn"))

    if re.search(r"\b\d+(?:\.\d+)?%?\b|[$£€]\s?\d", text):
        score += 5
        reasons.append((5, "Specific detail or number"))
    if any(term in lower for term in INTEREST_TERMS):
        score += 6
        reasons.append((6, "High-interest language"))

    # Speaking density and substance.
    if 100 <= wpm <= 205:
        score += 6
        reasons.append((6, "Good speaking density"))
    elif wpm < 65 or wpm > 250:
        score -= 9

    if 45 <= word_count <= 155:
        score += 6
    elif word_count < 28:
        score -= 12
    elif word_count > 190:
        score -= 7

    # Penalise filler-heavy and repetitive windows.
    unigram_fillers = sum(1 for word in words if word in FILLERS)
    phrase_fillers = sum(lower.count(filler) for filler in FILLERS if " " in filler)
    filler_ratio = (unigram_fillers + phrase_fillers) / max(word_count, 1)
    if filler_ratio > 0.07:
        score -= min(12, 5 + filler_ratio * 50)

    content_words = [w for w in words if len(w) > 3]
    if content_words:
        unique_ratio = len(set(content_words)) / len(content_words)
        if unique_ratio < 0.42:
            score -= 6

    # Penalise endings that audibly promise more context.
    ending_words = _words(ending[-100:])
    if ending_words and ending_words[-1] in TRAILING_DEPENDENCIES:
        score -= 12

    # Keep the most meaningful, non-duplicate explanations.
    dedup: list[str] = []
    for _weight, reason in sorted(reasons, reverse=True):
        if reason not in dedup:
            dedup.append(reason)
        if len(dedup) >= 4:
            break

    return max(1, min(98, round(score))), dedup


def _overlap_ratio(a: ClipCandidate, b: ClipCandidate) -> float:
    intersection = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    if intersection <= 0:
        return 0.0
    return intersection / max(1.0, min(a.end - a.start, b.end - b.start))


def _opening_signature(text: str) -> set[str]:
    return {w for w in _words(text)[:18] if len(w) > 3}


def _too_similar(a: ClipCandidate, b: ClipCandidate) -> bool:
    if _overlap_ratio(a, b) > 0.48:
        return True
    aw = _opening_signature(a.hook)
    bw = _opening_signature(b.hook)
    if not aw or not bw:
        return False
    return len(aw & bw) / max(1, min(len(aw), len(bw))) > 0.72


def rank_clip_candidates_local(
    segments: list[TranscriptSegment],
    max_clips: int,
) -> list[ClipCandidate]:
    """Local zero-credit clip selector tuned for complete short-form moments.

    Milestone 10 deliberately prioritises boundaries and narrative completeness over
    merely finding exciting words. Candidate windows start/end on transcript
    segments, score hooks + payoff + standalone context, then deduplicate heavily
    overlapping or near-identical moments.
    """
    if not segments:
        return []

    candidates: list[ClipCandidate] = []
    n = len(segments)

    for start_index in range(n):
        start_seg = segments[start_index]
        start = start_seg.start

        # Avoid obviously context-dependent starts unless a pause or hook makes them
        # plausible. We still allow them at a lower score so unusual speech is not lost.
        start_is_promising = (
            _starts_clean(start_seg.text)
            or _gap_before(segments, start_index) >= 0.45
            or any(h in _clean(start_seg.text).lower()[:120] for h in HOOK_PHRASES)
        )

        pieces: list[str] = []
        for end_index in range(start_index, min(n, start_index + 30)):
            seg = segments[end_index]
            pieces.append(seg.text)
            duration = seg.end - start

            if duration < 18:
                continue
            if duration > 65:
                break

            natural_end = _ends_clean(seg.text) or _gap_after(segments, end_index) >= 0.45
            in_sweet_spot = 26 <= duration <= 50

            # Prefer real endpoints. A sweet-spot fallback keeps transcripts with poor
            # punctuation from producing no candidates at all.
            if not natural_end and not (in_sweet_spot and end_index == min(n - 1, start_index + 29)):
                continue

            text = _clean(" ".join(pieces))
            score, reasons = _candidate_score(
                text=text,
                duration=duration,
                start_text=start_seg.text,
                end_text=seg.text,
                gap_before=_gap_before(segments, start_index),
                gap_after=_gap_after(segments, end_index),
            )
            if not start_is_promising:
                score = max(1, score - 7)

            # A tiny pad prevents the generated video from cutting the first/last phoneme.
            padded_start = max(0.0, start - 0.12)
            padded_end = seg.end + 0.16
            candidates.append(
                ClipCandidate(
                    start=round(padded_start, 2),
                    end=round(padded_end, 2),
                    title=generate_clip_copy_local(text, "auto").title,
                    social_caption=generate_clip_copy_local(text, "auto").social_caption,
                    hook=_first_sentence(text),
                    score=score,
                    reasons=reasons or ["Complete local moment"],
                )
            )

    # Score first; for equal scores prefer the tighter edit.
    candidates.sort(key=lambda c: (c.score, -(c.end - c.start)), reverse=True)

    selected: list[ClipCandidate] = []
    for candidate in candidates:
        if any(_too_similar(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_clips:
            break

    # Very short transcripts can fail the 18-second threshold. Return one usable range.
    if not selected and segments:
        text = _clean(" ".join(s.text for s in segments))
        duration = segments[-1].end - segments[0].start
        score, reasons = _candidate_score(
            text=text,
            duration=duration,
            start_text=segments[0].text,
            end_text=segments[-1].text,
            gap_before=10.0,
            gap_after=10.0,
        )
        selected.append(
            ClipCandidate(
                start=round(max(0.0, segments[0].start - 0.12), 2),
                end=round(segments[-1].end + 0.16, 2),
                title=generate_clip_copy_local(text, "auto").title,
                    social_caption=generate_clip_copy_local(text, "auto").social_caption,
                hook=_first_sentence(text),
                score=score,
                reasons=reasons or ["Best available local candidate"],
            )
        )

    return selected[:max_clips]
