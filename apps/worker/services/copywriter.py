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
    "regret", "realised", "realized", "learned", "lost", "won", "almost",
)

PAYOFF_CUES = (
    "that's why", "that is why", "the lesson", "the point is", "turns out",
    "in the end", "the answer", "which means", "so now", "i learned", "i realised",
    "i realized", "eventually",
)

CONTRAST_CUES = (" but ", " however ", " until ", " instead ", " turns out ", " except ")


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
        score += 6
    if any(term in lower for term in HIGH_INTEREST):
        score += 6
    if re.search(r"\b\d+(?:\.\d+)?%?\b|[$£€]\s?\d", sentence):
        score += 4
    if any(cue in lower for cue in PAYOFF_CUES):
        score += 5
    if any(cue in f" {lower} " for cue in CONTRAST_CUES):
        score += 3
    word_count = len(sentence.split())
    if 5 <= word_count <= 16:
        score += 4
    elif word_count > 24:
        score -= 2
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


def _supporting_sentence(text: str, core: str) -> str:
    sentences = _sentences(text)
    if len(sentences) < 2:
        return ""
    candidates = [sentence for sentence in sentences if _clean(sentence).lower() != _clean(core).lower()]
    if not candidates:
        return ""
    # Prefer a payoff / consequence sentence for the post caption rather than
    # repeating the same hook that became the title.
    for sentence in reversed(candidates):
        lower = sentence.lower()
        if any(cue in lower for cue in PAYOFF_CUES) or any(cue in f" {lower} " for cue in CONTRAST_CUES):
            return _strip_filler_start(sentence)
    return _strip_filler_start(candidates[-1])


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
        (r"^the reason (?:was|is)\s+", "The Real Reason: "),
        (r"^the secret (?:was|is)\s+", "The Secret: "),
        (r"^i was wrong about\s+", "I Was Wrong About "),
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

    core = _core_sentence(text)
    support = _supporting_sentence(text, core)
    core_clean = _truncate_words(_strip_filler_start(core), 18, 120)
    support_clean = _truncate_words(support, 18, 120) if support else ""

    # Avoid making the social caption a copy/paste of the title. Use the next useful
    # line from the dialogue as the payoff/context whenever possible.
    title_words = set(re.findall(r"[a-z0-9']+", title.lower()))
    core_words = set(re.findall(r"[a-z0-9']+", core_clean.lower()))
    overlap = len(title_words & core_words) / max(1, min(len(title_words), len(core_words)))
    first = support_clean if overlap > 0.72 and support_clean else core_clean

    if style == "cinematic":
        return _ensure_terminal(_sentence_case(_truncate_words(first, 22, 150)))

    if style == "viral":
        if support_clean and support_clean.lower() != first.lower():
            base = f"{first} {support_clean}"
        else:
            base = first
        return _ensure_terminal(_sentence_case(_truncate_words(base, 28, 180)))

    if support_clean and support_clean.lower() != first.lower():
        base = f"{_ensure_terminal(first)} {_ensure_terminal(support_clean)}"
    else:
        base = _ensure_terminal(first)
    return _ensure_terminal(_sentence_case(_truncate_words(base, 28, 185)))

def generate_clip_copy_local(text: str, style: TitleStyle = "auto") -> GeneratedCopy:
    normalized: TitleStyle = style if style in {"auto", "viral", "clean", "cinematic"} else "auto"
    title = _make_title(text, normalized)
    social_caption = _make_social_caption(text, normalized, title)
    return GeneratedCopy(title=title, social_caption=social_caption, style=normalized)
