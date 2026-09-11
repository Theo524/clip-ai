from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from models import TranscriptSegment

TitleStyle = Literal["auto", "viral", "clean", "cinematic"]

FILLER_STARTS = (
    "um ", "uh ", "erm ", "hmm ", "well ", "yeah ", "yes ", "okay ", "ok ",
    "so ", "and ", "but ", "like ", "you know ", "i mean ",
)

HIGH_INTEREST = (
    "mistake", "secret", "truth", "problem", "wrong", "never", "always",
    "money", "million", "billion", "failed", "failure", "risk", "crazy",
    "shocked", "surprised", "changed", "important", "dangerous", "love", "hate",
)

PAYOFF_CUES = (
    "that's why", "that is why", "the lesson", "the point is", "turns out",
    "in the end", "the answer", "which means", "so now", "i learned", "i realised",
    "i realized", "eventually",
)


@dataclass(frozen=True)
class GeneratedCopy:
    title: str
    social_caption: str
    style: TitleStyle


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def dialogue_for_range(segments: list[TranscriptSegment], start: float, end: float) -> str:
    parts = [
        segment.text.strip()
        for segment in segments
        if segment.end > start and segment.start < end and segment.text.strip()
    ]
    return _clean(" ".join(parts))


def _sentences(text: str) -> list[str]:
    cleaned = _clean(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part.strip(" \t\n\r\"“”") for part in parts if part.strip()]


def _strip_filler_start(text: str) -> str:
    cleaned = _clean(text).lstrip("\"“‘")
    lowered = cleaned.lower()
    changed = True
    while changed:
        changed = False
        for prefix in FILLER_STARTS:
            if lowered.startswith(prefix) and len(cleaned) > len(prefix) + 8:
                cleaned = cleaned[len(prefix):].lstrip(" ,.-")
                lowered = cleaned.lower()
                changed = True
                break
    return cleaned


def _truncate_words(text: str, max_words: int, max_chars: int) -> str:
    cleaned = _clean(text).strip(" .,!?:;–—")
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]).rstrip(" ,.!?:;–—")
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.!?:;–—")
    return cleaned


def _sentence_score(sentence: str, index: int, total: int) -> float:
    lower = sentence.lower()
    score = 0.0
    if index == 0:
        score += 4
    if "?" in sentence:
        score += 5
    if any(term in lower for term in HIGH_INTEREST):
        score += 5
    if re.search(r"\b\d+(?:\.\d+)?%?\b|[$£€]\s?\d", sentence):
        score += 3
    if any(cue in lower for cue in PAYOFF_CUES):
        score += 4
    word_count = len(sentence.split())
    if 5 <= word_count <= 18:
        score += 3
    if index == total - 1 and total > 1:
        score += 1
    return score


def _core_sentence(text: str) -> str:
    sentences = _sentences(text)
    if not sentences:
        return _strip_filler_start(text)
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (_sentence_score(item[1], item[0], len(sentences)), -item[0]),
        reverse=True,
    )
    return _strip_filler_start(ranked[0][1])


def _sentence_case(text: str) -> str:
    cleaned = _clean(text)
    if not cleaned:
        return cleaned
    return cleaned[0].upper() + cleaned[1:]


def _smart_title_case(text: str) -> str:
    small = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
    words = text.split()
    out: list[str] = []
    for i, word in enumerate(words):
        plain = word.strip(".,!?;:")
        if plain.isupper() and len(plain) <= 5:
            out.append(word)
            continue
        if i > 0 and plain.lower() in small:
            out.append(word.lower())
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)


def _make_title(text: str, style: TitleStyle) -> str:
    core = _core_sentence(text)
    core = re.sub(r"^(here(?:'s| is)\s+)(?:the\s+)?", "", core, flags=re.I)

    # Dialogue-like statements become more title-like without inventing new facts.
    replacements = (
        (r"^the biggest mistake i (?:made|make) (?:was|is)\s+", "My Biggest Mistake: "),
        (r"^the biggest mistake (?:was|is)\s+", "The Biggest Mistake: "),
        (r"^the problem (?:was|is)\s+", "The Problem: "),
        (r"^the truth (?:was|is)\s+", "The Truth: "),
        (r"^i learned (?:that\s+)?", "What I Learned: "),
        (r"^i realised (?:that\s+)?", "What I Realised: "),
        (r"^i realized (?:that\s+)?", "What I Realized: "),
    )
    for pattern, replacement in replacements:
        if re.search(pattern, core, flags=re.I):
            core = re.sub(pattern, replacement, core, count=1, flags=re.I)
            break

    if style == "cinematic":
        title = _truncate_words(core, 7, 48)
        return _sentence_case(title)

    if style == "clean":
        title = _truncate_words(core, 10, 62)
        return _sentence_case(title)

    # Auto intentionally leans clean unless the dialogue itself contains a clear
    # high-interest hook. Viral is punchier in casing, not more sensational in facts.
    effective = style
    if style == "auto":
        effective = "viral" if any(term in core.lower() for term in HIGH_INTEREST) or "?" in core else "clean"

    title = _truncate_words(core, 9 if effective == "viral" else 10, 58)
    if effective == "viral":
        title = title.rstrip(".")
        if "?" not in title:
            title = _smart_title_case(title)
    else:
        title = _sentence_case(title)
    return title or "Strong moment"


def _ensure_terminal(text: str) -> str:
    cleaned = _clean(text).rstrip(" ,;:–—")
    if cleaned and cleaned[-1] not in ".!?…":
        cleaned += "."
    return cleaned


def _make_social_caption(text: str, style: TitleStyle, title: str) -> str:
    sentences = _sentences(text)
    if not sentences:
        return title

    first = _strip_filler_start(sentences[0])
    payoff = ""
    for sentence in reversed(sentences[1:]):
        lower = sentence.lower()
        if any(cue in lower for cue in PAYOFF_CUES):
            payoff = sentence
            break
    if not payoff and len(sentences) > 1:
        payoff = sentences[-1]

    first = _truncate_words(first, 18, 120)
    payoff = _truncate_words(payoff, 18, 120) if payoff else ""

    if style == "cinematic":
        # Keep cinematic copy restrained and dialogue-led.
        base = first
        if payoff and payoff.lower() != first.lower():
            base = f"{first} — {payoff}"
        return _ensure_terminal(_sentence_case(_truncate_words(base, 26, 170)))

    if style == "viral":
        base = first
        if payoff and payoff.lower() != first.lower():
            base = f"{first} — {payoff}"
        return _ensure_terminal(_sentence_case(_truncate_words(base, 30, 185)))

    if payoff and payoff.lower() != first.lower():
        first_sentence = _ensure_terminal(first)
        payoff_sentence = _ensure_terminal(payoff)
        base = f"{first_sentence} {payoff_sentence}"
    else:
        base = _ensure_terminal(first)
    return _ensure_terminal(_sentence_case(_truncate_words(base, 30, 190)))


def generate_clip_copy_local(text: str, style: TitleStyle = "auto") -> GeneratedCopy:
    normalized: TitleStyle = style if style in {"auto", "viral", "clean", "cinematic"} else "auto"
    title = _make_title(text, normalized)
    social_caption = _make_social_caption(text, normalized, title)
    return GeneratedCopy(title=title, social_caption=social_caption, style=normalized)
