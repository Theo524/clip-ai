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
) -> tuple[int, list[str], dict[str, int], str]:
    lower = text.lower()
    words = _words(text)
    word_count = len(words)
    wpm = word_count / max(duration, 1.0) * 60
    opening = _clean(start_text).lower().lstrip('"“‘')
    ending = _clean(end_text).lower()

    # Keep the proven v10 heuristic, but expose the editorial dimensions separately
    # and blend them back into the final score. This makes the ranking easier to
    # understand and less dependent on one lucky keyword.
    score = 36.0
    reasons: list[tuple[int, str]] = []

    hook = 35.0
    standalone = 35.0
    payoff = 28.0
    retention = 38.0
    clarity = 42.0

    if 24 <= duration <= 48:
        score += 15
        retention += 24
        reasons.append((15, "Strong Shorts length"))
    elif 18 <= duration <= 60:
        score += 8
        retention += 13
        reasons.append((8, "Usable short-form length"))
    else:
        score -= min(18, abs(duration - 36) * 0.65)
        retention -= 12

    clean_start = _starts_clean(start_text)
    if clean_start:
        score += 8
        hook += 10
        standalone += 20
        clarity += 7
        reasons.append((8, "Clean standalone opening"))
    else:
        score -= 15
        hook -= 18
        standalone -= 24

    strong_hook = any(opening.startswith(p) or p in opening[:110] for p in HOOK_PHRASES)
    if strong_hook:
        score += 14
        hook += 35
        retention += 8
        reasons.append((14, "Strong opening hook"))
    if "?" in _clean(start_text)[:180]:
        score += 8
        hook += 20
        retention += 7
        reasons.append((8, "Question-led hook"))
    if re.search(r"\b\d+(?:\.\d+)?%?\b|[$£€]\s?\d", _clean(start_text)[:220]):
        score += 5
        hook += 10
        clarity += 5
        reasons.append((5, "Specific opening detail"))

    if gap_before >= 0.35:
        score += 4
        standalone += 10
        clarity += 4
        reasons.append((4, "Natural start boundary"))
    clean_end = _ends_clean(end_text)
    if clean_end:
        score += 8
        standalone += 16
        payoff += 8
        clarity += 8
        reasons.append((8, "Clean ending"))
    else:
        score -= 12
        standalone -= 18
        payoff -= 12
    if gap_after >= 0.35:
        score += 4
        standalone += 8
        payoff += 5
        reasons.append((4, "Natural end boundary"))

    latter_half = lower[len(lower) // 2 :]
    ending_lower = _clean(end_text).lower()
    payoff_positions = [lower.rfind(cue) for cue in PAYOFF_PHRASES if cue in lower]
    last_payoff = max(payoff_positions) if payoff_positions else -1
    payoff_in_ending = any(cue in ending_lower for cue in PAYOFF_PHRASES)
    if payoff_in_ending:
        score += 13
        payoff += 45
        retention += 8
        reasons.append((13, "Ends on a clear payoff"))
    elif any(cue in latter_half for cue in PAYOFF_PHRASES):
        score += 7
        payoff += 28
        reasons.append((7, "Contains a payoff or takeaway"))
        if last_payoff >= 0:
            trailing_fraction = (len(lower) - last_payoff) / max(len(lower), 1)
            if trailing_fraction > 0.20:
                score -= 18
                payoff -= 20
                retention -= 8
    if not _starts_clean(end_text) and not payoff_in_ending:
        score -= 10
        payoff -= 12
    if any(cue in lower for cue in PIVOT_PHRASES):
        score += 6
        payoff += 12
        retention += 8
        reasons.append((6, "Has a story/idea turn"))

    if re.search(r"\b\d+(?:\.\d+)?%?\b|[$£€]\s?\d", text):
        score += 5
        clarity += 8
        retention += 4
        reasons.append((5, "Specific detail or number"))
    if any(term in lower for term in INTEREST_TERMS):
        score += 6
        retention += 15
        hook += 7
        reasons.append((6, "High-interest language"))

    if 100 <= wpm <= 205:
        score += 6
        clarity += 10
        retention += 10
        reasons.append((6, "Good speaking density"))
    elif wpm < 65 or wpm > 250:
        score -= 9
        clarity -= 15
        retention -= 12

    if 45 <= word_count <= 155:
        score += 6
        clarity += 10
    elif word_count < 28:
        score -= 12
        clarity -= 18
        payoff -= 8
    elif word_count > 190:
        score -= 7
        clarity -= 10

    unigram_fillers = sum(1 for word in words if word in FILLERS)
    phrase_fillers = sum(lower.count(filler) for filler in FILLERS if " " in filler)
    filler_ratio = (unigram_fillers + phrase_fillers) / max(word_count, 1)
    if filler_ratio > 0.07:
        penalty = min(12, 5 + filler_ratio * 50)
        score -= penalty
        clarity -= penalty * 1.5
        retention -= penalty

    content_words = [w for w in words if len(w) > 3]
    if content_words:
        unique_ratio = len(set(content_words)) / len(content_words)
        if unique_ratio < 0.42:
            score -= 6
            clarity -= 10
            retention -= 8
        elif unique_ratio > 0.66:
            clarity += 5

    ending_words = _words(ending[-100:])
    if ending_words and ending_words[-1] in TRAILING_DEPENDENCIES:
        score -= 12
        payoff -= 18
        standalone -= 10

    breakdown = {
        "Hook": max(1, min(99, round(hook))),
        "Standalone": max(1, min(99, round(standalone))),
        "Payoff": max(1, min(99, round(payoff))),
        "Retention": max(1, min(99, round(retention))),
        "Clarity": max(1, min(99, round(clarity))),
    }
    weighted_quality = (
        breakdown["Hook"] * 0.25
        + breakdown["Standalone"] * 0.22
        + breakdown["Payoff"] * 0.22
        + breakdown["Retention"] * 0.19
        + breakdown["Clarity"] * 0.12
    )
    score = score * 0.62 + weighted_quality * 0.38

    dedup: list[str] = []
    for _weight, reason in sorted(reasons, reverse=True):
        if reason not in dedup:
            dedup.append(reason)
        if len(dedup) >= 4:
            break

    strongest = sorted(breakdown.items(), key=lambda item: item[1], reverse=True)[:2]
    weak = min(breakdown.items(), key=lambda item: item[1])
    note = f"Best at {strongest[0][0].lower()} + {strongest[1][0].lower()}."
    if weak[1] < 45:
        note += f" {weak[0]} is the main trade-off."

    return max(1, min(98, round(score))), dedup, breakdown, note

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
            score, reasons, breakdown, editor_note = _candidate_score(
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
            generated_copy = generate_clip_copy_local(text, "auto")
            candidates.append(
                ClipCandidate(
                    start=round(padded_start, 2),
                    end=round(padded_end, 2),
                    title=generated_copy.title,
                    social_caption=generated_copy.social_caption,
                    hook=_first_sentence(text),
                    score=score,
                    reasons=reasons or ["Complete local moment"],
                    score_breakdown=breakdown,
                    editor_note=editor_note,
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
        score, reasons, breakdown, editor_note = _candidate_score(
            text=text,
            duration=duration,
            start_text=segments[0].text,
            end_text=segments[-1].text,
            gap_before=10.0,
            gap_after=10.0,
        )
        generated_copy = generate_clip_copy_local(text, "auto")
        selected.append(
            ClipCandidate(
                start=round(max(0.0, segments[0].start - 0.12), 2),
                end=round(segments[-1].end + 0.16, 2),
                title=generated_copy.title,
                social_caption=generated_copy.social_caption,
                hook=_first_sentence(text),
                score=score,
                reasons=reasons or ["Best available local candidate"],
                score_breakdown=breakdown,
                editor_note=editor_note,
            )
        )

    return selected[:max_clips]
