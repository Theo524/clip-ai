from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from models import TranscriptSegment

TitleStyle = Literal["auto", "viral", "clean", "cinematic"]

FILLER_STARTS = (
    "um ", "uh ", "erm ", "hmm ", "well ", "yeah ", "yes ", "okay ", "ok ",
    "so ", "and ", "but ", "like ", "you know ", "i mean ", "basically ",
)

HIGH_INTEREST = (
    "mistake", "secret", "truth", "problem", "wrong", "never", "always",
    "money", "million", "billion", "failed", "failure", "risk", "crazy",
    "shocked", "surprised", "changed", "important", "dangerous", "love", "hate",
    "regret", "realised", "realized", "learned", "lost", "won", "almost",
    "revealed", "discovered", "found out", "escaped", "saved", "betrayed",
)

PAYOFF_CUES = (
    "that's why", "that is why", "the lesson", "the point is", "turns out",
    "in the end", "the answer", "which means", "so now", "i learned", "i realised",
    "i realized", "eventually", "finally", "actually",
)

CONTRAST_CUES = (" but ", " however ", " until ", " instead ", " turns out ", " except ", " yet ")

STOPWORDS = {
    "about", "after", "again", "against", "almost", "also", "always", "because", "before", "being",
    "between", "could", "didnt", "doesnt", "doing", "dont", "even", "every", "from", "going", "have",
    "having", "here", "into", "just", "like", "maybe", "more", "most", "much", "really", "right", "said",
    "same", "should", "something", "still", "than", "that", "their", "them", "then", "there", "these", "they",
    "thing", "think", "this", "those", "through", "very", "want", "wasnt", "what", "when", "where", "which",
    "while", "with", "would", "youre", "your", "actually", "basically", "literally", "people", "person", "things",
    "everyone", "someone", "anything", "everything", "ready", "happened", "cannot", "couldnt", "wouldnt", "thought",
    "told", "made", "first", "next", "quickly", "slowly", "started", "stopped", "began", "came", "went", "getting",
    "biggest", "hiding", "missed", "believe", "matter", "spent", "spending", "returned", "protect", "protected",
    "that's", "thats",
}

# One broad category tag is enough. v23.4 deliberately avoids padding metadata with
# #Shorts / #AnimeClips / #PodcastClips-style filler when a more specific tag exists.
CONTENT_TAGS = {
    "podcast": ("Podcast",),
    "anime": ("Anime",),
    "film-tv": (),
    "documentary": ("Documentary",),
    "meme-comedy": ("Comedy",),
    "gameplay": ("Gaming",),
    "other": (),
}

MOMENT_TAGS = {
    "funny": "Funny",
    "emotional": "Emotional",
    "action": "Action",
    "reveal": "Reveal",
    "argument": "Debate",
    "reaction": "Reaction",
    # "informative" is intentionally not turned into #LearnSomething; it reads like
    # generic auto-generated metadata and usually adds no discovery value.
}

WEAK_TAG_WORDS = {
    "looked", "looks", "looking", "walked", "walking", "said", "says", "saying",
    "absolutely", "literally", "really", "basically", "actually", "probably", "maybe",
    "came", "come", "coming", "went", "going", "gets", "got", "getting", "made", "make",
    "thought", "think", "thinking", "knew", "know", "knows", "wanted", "wants", "want",
    "told", "tell", "telling", "heard", "hear", "seeing", "seen", "saw", "just", "very",
    "agreed", "agree", "decided", "trying", "tried", "worked", "working", "understood",
    "proved", "proven", "final", "entire",
    "everyone", "someone", "something", "anything", "nothing", "everything", "people",
}

TITLE_TRAILING_WEAK = {
    "a", "an", "the", "and", "but", "or", "because", "so", "to", "of", "for", "with",
    "at", "in", "on", "from", "by", "that", "this", "these", "those", "who", "which",
}


@dataclass(frozen=True)
class GeneratedCopy:
    title: str
    description: str
    hashtags: tuple[str, ...]
    social_caption: str
    style: TitleStyle
    grounded_terms: tuple[str, ...] = ()


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
    parts = re.split(r"(?<=[.!?…])\s+", cleaned)
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
    cleaned = re.sub(r"^(?:i think|i guess|i feel like|we think|you see)\s+", "", cleaned, flags=re.I)
    return cleaned


def _truncate_words(text: str, max_words: int, max_chars: int) -> str:
    cleaned = _clean(text).strip(" .,!?:;–—")
    words = cleaned.split()
    if len(words) > max_words:
        words = words[:max_words]
        while len(words) > 3 and re.sub(r"[^A-Za-z']", "", words[-1]).lower() in TITLE_TRAILING_WEAK:
            words.pop()
        cleaned = " ".join(words).rstrip(" ,.!?:;–—")
    if len(cleaned) > max_chars:
        head = cleaned[:max_chars]
        cleaned = head.rsplit(" ", 1)[0].rstrip(" ,.!?:;–—") if " " in head else head.rstrip(" ,.!?:;–—")
        words = cleaned.split()
        while len(words) > 3 and re.sub(r"[^A-Za-z']", "", words[-1]).lower() in TITLE_TRAILING_WEAK:
            words.pop()
        cleaned = " ".join(words)
    return cleaned


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) >= 4 and w not in STOPWORDS]


def _topic_counts(text: str) -> Counter[str]:
    return Counter(_tokens(text))


def _sentence_score(sentence: str, index: int, total: int, topic_counts: Counter[str] | None = None) -> float:
    lower = sentence.lower()
    score = 0.0
    if index == 0:
        score += 3
    if "?" in sentence:
        score += 4
    if any(term in lower for term in HIGH_INTEREST):
        score += 8
    if re.search(r"\b\d+(?:\.\d+)?%?\b|[$£€]\s?\d", sentence):
        score += 3
    if any(cue in lower for cue in PAYOFF_CUES):
        score += 5
    if any(cue in f" {lower} " for cue in CONTRAST_CUES):
        score += 3
    word_count = len(sentence.split())
    if 6 <= word_count <= 20:
        score += 5
    elif word_count > 30:
        score -= 4
    if index == total - 1 and total > 1:
        score += 1
    if topic_counts:
        topical = sum(min(3, topic_counts[token]) for token in set(_tokens(sentence)))
        score += min(7.0, topical * 0.55)
    # A title based on a dangling fragment is usually worse than a calmer complete thought.
    if re.search(r"\b(?:and|but|because|so|then|which|that)\s*$", lower.rstrip(" .!?")):
        score -= 8
    return score


def _core_sentence(text: str, local_context: str = "") -> str:
    sentences = _sentences(text)
    if not sentences:
        return _strip_filler_start(text)
    topic_counts = _topic_counts(f"{text} {local_context}")
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (_sentence_score(item[1], item[0], len(sentences), topic_counts), -item[0]),
        reverse=True,
    )
    return _strip_filler_start(ranked[0][1])


def _supporting_sentence(text: str, core: str, local_context: str = "") -> str:
    sentences = _sentences(text)
    if len(sentences) < 2:
        return ""
    core_tokens = set(_tokens(core))
    candidates = []
    for sentence in sentences:
        if _clean(sentence).lower() == _clean(core).lower():
            continue
        sentence_tokens = set(_tokens(sentence))
        overlap = len(core_tokens & sentence_tokens) / max(1, min(len(core_tokens), len(sentence_tokens))) if core_tokens and sentence_tokens else 0.0
        if overlap >= 0.88:
            continue
        candidates.append(sentence)
    if not candidates:
        return ""
    topic_counts = _topic_counts(f"{text} {local_context}")
    ranked = sorted(
        enumerate(candidates),
        key=lambda item: (_sentence_score(item[1], item[0], len(candidates), topic_counts), item[0]),
        reverse=True,
    )
    return _strip_filler_start(ranked[0][1])


def _sentence_case(text: str) -> str:
    cleaned = _clean(text)
    return cleaned[:1].upper() + cleaned[1:] if cleaned else cleaned


def _smart_title_case(text: str) -> str:
    small = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
    words = text.split()
    out: list[str] = []
    for i, word in enumerate(words):
        plain = word.strip(".,!?;:")
        if plain.isupper() and len(plain) <= 5:
            out.append(word)
        elif i > 0 and plain.lower() in small:
            out.append(word.lower())
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)


def _subject_label(subject_hint: str | None) -> str:
    clean = _clean(subject_hint or "")
    if not clean:
        return ""
    # A comma often separates the show/program from episode notes supplied by the user.
    return clean.split(",", 1)[0].strip()[:64]


def _restore_trusted_term_case(text: str, subject_hint: str | None) -> str:
    """Restore the exact casing of a user-supplied show/program/subject label.

    This is deliberately conservative: M5 never guesses a name from a filename or
    outside knowledge. It only fixes casing when the trusted label already appears in
    the generated text case-insensitively.
    """
    subject = _subject_label(subject_hint)
    cleaned = _clean(text)
    if not subject or not cleaned:
        return cleaned
    return re.sub(re.escape(subject), lambda _match: subject, cleaned, flags=re.I)


def _compress_title_headline(headline: str, context: str = "") -> str:
    """Prefer a complete, meaningful clause over a blindly truncated sentence."""
    clean = _clean(headline).strip(" ,;:–—")
    if len(clean.split()) <= 11 and len(clean) <= 72:
        return clean
    pieces = [
        piece.strip(" ,;:–—")
        for piece in re.split(r"(?:[,;]|[–—]|\b(?:but|however|until|instead|yet|then)\b)", clean, flags=re.I)
        if piece.strip(" ,;:–—")
    ]
    candidates: list[tuple[float, int, str]] = []
    topic_counts = _topic_counts(f"{headline} {context}")
    for index, piece in enumerate(pieces):
        words = piece.split()
        if not 4 <= len(words) <= 20:
            continue
        tail = re.sub(r"[^A-Za-z']", "", words[-1]).lower()
        if tail in TITLE_TRAILING_WEAK:
            continue
        score = _sentence_score(piece, index, len(pieces), topic_counts)
        if any(cue.strip() in piece.lower() for cue in PAYOFF_CUES):
            score += 3
        candidates.append((score, -index, piece))
    if candidates:
        return max(candidates)[2]
    return clean


def _truncate_title(text: str, max_words: int, max_chars: int) -> str:
    """Make a title-shaped phrase without leaving a dangling connector."""
    clean = _clean(text).strip(" .,!?:;–—")
    if len(clean.split()) <= max_words and len(clean) <= max_chars:
        return clean
    words = clean.split()
    kept: list[str] = []
    for word in words:
        candidate = " ".join([*kept, word])
        if kept and (len(kept) >= max_words or len(candidate) > max_chars):
            break
        kept.append(word)
    while len(kept) > 3 and re.sub(r"[^A-Za-z']", "", kept[-1]).lower() in TITLE_TRAILING_WEAK:
        kept.pop()
    return " ".join(kept).rstrip(" ,.!?:;–—")


def _headline_from_sentence(core: str) -> str:
    headline = _strip_filler_start(core).strip(" \"“”'")
    headline = re.sub(r"^(?:here(?:'s| is)\s+)(?:the\s+)?", "", headline, flags=re.I)

    transformations = (
        (r"^the biggest mistake i (?:made|make) (?:was|is)\s+", "My Biggest Mistake: "),
        (r"^the biggest mistake (?:was|is)\s+", "The Biggest Mistake: "),
        (r"^the problem (?:was|is)\s+", ""),
        (r"^the truth (?:was|is)\s+", ""),
        (r"^the reason (?:was|is)\s+", ""),
        (r"^the secret (?:was|is)\s+", ""),
        (r"^i was wrong about\s+", "I Was Wrong About "),
        (r"^i learned (?:that\s+)?", "What I Learned: "),
        (r"^i realised (?:that\s+)?", "What I Realised: "),
        (r"^i realized (?:that\s+)?", "What I Realized: "),
        (r"^turns out(?: that)?\s+", ""),
        (r"^it turns out(?: that)?\s+", ""),
    )
    for pattern, replacement in transformations:
        if re.search(pattern, headline, flags=re.I):
            return re.sub(pattern, replacement, headline, count=1, flags=re.I)

    causal_action = re.match(
        r"^(?:i|we|they|he|she)\s+(?:came|went|stayed|left|did|did it|returned).{0,42}?\s+because\s+(.+)$",
        headline, flags=re.I,
    )
    if causal_action and len(causal_action.group(1).split()) >= 3:
        return causal_action.group(1).strip(" ,.-")

    # "X is because Y" is usually more useful as a compact Why headline than raw dialogue.
    because = re.match(r"^(.{8,70}?)\s+(?:is|was|happened)\s+because\s+(.+)$", headline, flags=re.I)
    if because and len(because.group(1).split()) >= 3:
        return f"Why {because.group(1).strip(' ,.-')}"

    when_clause = re.match(r"^(when\s+[^,]{10,64}),\s+.+$", headline, flags=re.I)
    if when_clause and 4 <= len(when_clause.group(1).split()) <= 10:
        return when_clause.group(1)

    return headline


def _make_title(text: str, style: TitleStyle, *, local_context: str = "", subject_hint: str | None = None,
                content_type: str | None = None) -> str:
    core = _core_sentence(text, local_context)
    headline = _compress_title_headline(_headline_from_sentence(core), local_context)
    subject = _subject_label(subject_hint)

    max_words, max_chars = (7, 52) if style == "cinematic" else (10, 66)
    title = _truncate_title(headline, max_words, max_chars)

    effective = style
    if style == "auto":
        effective = "viral" if any(term in core.lower() for term in HIGH_INTEREST) or "?" in core else "clean"

    if effective == "viral":
        title = _smart_title_case(title.rstrip(".")) if "?" not in title else _sentence_case(title)
    else:
        title = _sentence_case(title)

    # For programme-based material a short trusted subject hint makes an otherwise vague
    # headline self-contained. We only use text explicitly supplied by the user.
    vague_start = re.match(r"^(?:he|she|they|it|this|that|we|i)\b", title, flags=re.I)
    if subject and content_type in {"anime", "film-tv", "documentary"} and (vague_start or len(title.split()) <= 6):
        room = 72 - len(subject) - 3
        if room >= 20 and subject.lower() not in title.lower():
            title = f"{subject}: {_truncate_words(title, 8, room)}"

    title = _restore_trusted_term_case(title, subject_hint)
    return title[:78].rstrip(" ,;:–—") or "Strong moment"


def _ensure_terminal(text: str) -> str:
    cleaned = _clean(text).rstrip(" ,;:–—")
    if cleaned and cleaned[-1] not in ".!?…":
        cleaned += "."
    return cleaned


def _similarity(left: str, right: str) -> float:
    a, b = set(_tokens(left)), set(_tokens(right))
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


_DESCRIPTION_TRAILING_WEAK = TITLE_TRAILING_WEAK | {
    "i", "we", "you", "he", "she", "they", "it", "is", "was", "are", "were",
    "be", "been", "have", "has", "had", "do", "did", "can", "could", "would",
    "should", "will", "might", "must", "my", "your", "his", "her", "their",
}


def _description_fragment(text: str, max_words: int, max_chars: int) -> str:
    """Shorten a source sentence at a natural clause edge instead of mid-thought."""
    clean = _clean(text).strip(' "“”')
    if len(clean.split()) <= max_words and len(clean) <= max_chars:
        return clean
    # First prefer a real punctuation boundary that fits. This avoids output such as
    # "...the design was wrong and we." when the source sentence is long.
    boundaries = [m.end() for m in re.finditer(r"[,;:–—]", clean)]
    fitting = [pos for pos in boundaries if 28 <= pos <= max_chars and len(clean[:pos].split()) <= max_words]
    if fitting:
        cut = clean[:max(fitting)].rstrip(" ,;:–—")
        if len(cut.split()) >= 5:
            return cut
    words = clean.split()
    kept: list[str] = []
    for word in words:
        candidate = " ".join([*kept, word])
        if kept and (len(kept) >= max_words or len(candidate) > max_chars):
            break
        kept.append(word)
    while len(kept) > 4 and re.sub(r"[^A-Za-z']", "", kept[-1]).lower() in _DESCRIPTION_TRAILING_WEAK:
        kept.pop()
    return " ".join(kept).rstrip(" ,;:–—")


def _make_description(
    text: str, title: str, style: TitleStyle, *, local_context: str = "",
    content_type: str | None = None, subject_hint: str | None = None
) -> str:
    core = _core_sentence(text, local_context)
    support = _supporting_sentence(text, core, local_context)
    candidates = [_strip_filler_start(core)]
    if support:
        candidates.append(_strip_filler_start(support))

    # Prefer a sentence that adds information rather than just restating the headline.
    ordered = sorted(candidates, key=lambda value: (_similarity(value, title), -len(value)))
    first = _description_fragment(ordered[0], 23, 150)
    second = ""
    if len(ordered) > 1 and _similarity(ordered[1], first) < 0.78:
        second = _description_fragment(ordered[1], 20, 125)

    content = (content_type or "other").lower().strip()
    # Film/anime social copy stays restrained and scene-grounded. Avoid canned
    # summaries; preserve trusted subject casing only when that label is actually said.
    if style == "cinematic" or content in {"anime", "film-tv"}:
        value = _ensure_terminal(_sentence_case(_description_fragment(first, 22, 150)))
        return _restore_trusted_term_case(value, subject_hint)
    if content == "meme-comedy":
        value = _ensure_terminal(_sentence_case(_description_fragment(first, 18, 120)))
        return _restore_trusted_term_case(value, subject_hint)
    description = _ensure_terminal(_sentence_case(first))
    if second and content in {"podcast", "documentary", "other", "gameplay"}:
        description = f"{description} {_ensure_terminal(_sentence_case(second))}"
    value = _ensure_terminal(_truncate_words(description, 36 if style == "viral" else 40, 240))
    return _restore_trusted_term_case(value, subject_hint)


def _hashtag(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value)
    if not words:
        return ""
    joined = "".join(word[:1].upper() + word[1:] for word in words)
    return f"#{joined[:36]}" if joined else ""


def _specific_topics(text: str, local_context: str, subject_hint: str | None, title: str) -> list[str]:
    counts = _topic_counts(text)
    local_counts = _topic_counts(local_context)
    subject_tokens = set(_tokens(subject_hint or ""))
    title_tokens = set(_tokens(title))
    scores: list[tuple[float, str]] = []
    for token, count in counts.items():
        if token in subject_tokens or token.isdigit() or len(token) < 5 or token in HIGH_INTEREST or token in WEAK_TAG_WORDS:
            continue
        score = count * 2.0 + min(2, local_counts.get(token, 0)) * 0.45
        if token in title_tokens:
            score += 3.2
        # Free-form hashtags should describe the subject, not random connective dialogue.
        if count < 2 and token not in title_tokens:
            continue
        scores.append((score, token))
    scores.sort(reverse=True)
    return [token for _, token in scores[:2]]

def _make_hashtags(text: str, *, local_context: str = "", subject_hint: str | None = None,
                   content_type: str | None = None, moment_type: str | None = None, title: str = "") -> tuple[str, ...]:
    tags: list[str] = []
    subject = _subject_label(subject_hint)
    if subject:
        tags.append(_hashtag(subject))
    for value in CONTENT_TAGS.get(content_type or "other", CONTENT_TAGS["other"]):
        tags.append(_hashtag(value))
    if moment_type and moment_type in MOMENT_TAGS:
        tags.append(_hashtag(MOMENT_TAGS[moment_type]))
    for token in _specific_topics(text, local_context, subject_hint, title):
        tags.append(_hashtag(token))
    clean: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        key = tag.lower()
        if tag and key not in seen:
            clean.append(tag)
            seen.add(key)
        if len(clean) >= 5:
            break
    return tuple(clean)


def _grounded_terms(text: str, local_context: str, subject_hint: str | None) -> tuple[str, ...]:
    terms: list[str] = []
    subject = _subject_label(subject_hint)
    if subject:
        terms.append(subject)
    # Capitalized multi-letter words already present in source context are safe to preserve;
    # Whisper often removes casing, so subject_hint remains the authoritative name source.
    generic_capitals = {"the", "this", "that", "that's", "they", "there", "when", "what", "where", "but", "and", "nobody", "someone", "everyone", "because", "after", "before", "finally"}
    for match in re.findall(r"\b[A-Z][A-Za-z0-9'’-]{2,}\b", f"{text} {local_context}"):
        if match.lower() in generic_capitals:
            continue
        if match.lower() not in {term.lower() for term in terms}:
            terms.append(match)
        if len(terms) >= 6:
            break
    return tuple(terms)


def _compose_social(description: str, hashtags: tuple[str, ...]) -> str:
    tags = " ".join(hashtags)
    return f"{description}\n\n{tags}".strip() if tags else description


def generate_clip_copy_local(
    text: str,
    style: TitleStyle = "auto",
    *,
    local_context: str = "",
    subject_hint: str | None = None,
    content_type: str | None = None,
    moment_type: str | None = None,
) -> GeneratedCopy:
    normalized: TitleStyle = style if style in {"auto", "viral", "clean", "cinematic"} else "auto"
    clip_text = _clean(text)
    nearby = _clean(local_context)
    content = (content_type or "other").lower().strip()
    # Auto metadata should match the medium. Film/anime titles are restrained by default;
    # meme/comedy is punchier; the other categories keep the existing adaptive choice.
    effective_style: TitleStyle = normalized
    if normalized == "auto" and content in {"anime", "film-tv"}:
        effective_style = "cinematic"
    elif normalized == "auto" and content == "meme-comedy":
        effective_style = "viral"
    title = _make_title(
        clip_text, effective_style, local_context=nearby, subject_hint=subject_hint, content_type=content_type,
    )
    description = _make_description(
        clip_text, title, effective_style, local_context=nearby, content_type=content_type, subject_hint=subject_hint
    )
    hashtags = _make_hashtags(
        clip_text, local_context=nearby, subject_hint=subject_hint, content_type=content_type, moment_type=moment_type, title=title,
    )
    return GeneratedCopy(
        title=title,
        description=description,
        hashtags=hashtags,
        social_caption=_compose_social(description, hashtags),
        style=normalized,
        grounded_terms=_grounded_terms(clip_text, nearby, subject_hint),
    )
