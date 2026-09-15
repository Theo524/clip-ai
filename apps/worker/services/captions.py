from dataclasses import dataclass
from pathlib import Path
import re

from models import TranscriptSegment, TranscriptWord
from services.layouts import normalize_frame_size, picture_window


STYLE_CONFIG = {
    "viral": {
        "font": "Trebuchet MS",
        "size": 58,
        "max_words": 5,
        "max_chars": 31,
        "max_duration": 2.7,
        "pause_break": 0.46,
        "primary": "&H00FFFFFF",
        "active": "&H0048E8FF",
        "outline": 5,
        "shadow": 2,
    },
    "cinematic": {
        "font": "Segoe UI Semibold",
        "size": 38,
        "max_words": 10,
        "max_chars": 52,
        "max_duration": 4.4,
        "pause_break": 0.72,
        "primary": "&H00FFFFFF",
        "active": "&H00FFFFFF",
        "outline": 2,
        "shadow": 1,
    },
    "clean": {
        "font": "Arial",
        "size": 44,
        "max_words": 8,
        "max_chars": 44,
        "max_duration": 3.6,
        "pause_break": 0.62,
        "primary": "&H00FFFFFF",
        "active": "&H00FFFFFF",
        "outline": 3,
        "shadow": 1,
    },
    "meme": {
        "font": "Impact",
        "size": 54,
        "max_words": 5,
        "max_chars": 32,
        "max_duration": 2.8,
        "pause_break": 0.46,
        "primary": "&H00FFFFFF",
        "active": "&H0000D7FF",
        "outline": 5,
        "shadow": 1,
    },
}


def _effective_style_config(style: str, content_type: str | None = None) -> dict:
    """Return a copy of the visual/density config with content-aware tuning."""
    cfg = dict(STYLE_CONFIG[style])
    content = (content_type or "auto").lower().strip()
    if content == "anime" and style == "cinematic":
        # Anime works best with restrained, low text that leaves the artwork readable.
        cfg.update(size=36, max_words=7, max_chars=38, max_duration=3.8, pause_break=0.76)
    elif content == "film-tv" and style == "cinematic":
        cfg.update(size=37, max_words=8, max_chars=44, max_duration=4.0, pause_break=0.74)
    elif content == "documentary" and style in {"clean", "cinematic"}:
        cfg.update(max_words=8, max_chars=46, max_duration=4.2)
    elif content == "meme-comedy" and style == "viral":
        cfg.update(max_words=5, max_chars=30, max_duration=2.5, pause_break=0.42)
    return cfg


_FILLER_WORDS = {"um", "uh", "erm", "er", "hmm", "mm", "uhm"}
_WEAK_EDGE_WORDS = {
    "and", "but", "or", "so", "because", "if", "then", "that", "which", "who",
    "to", "of", "for", "with", "at", "from", "by", "as", "a", "an", "the",
}
_SENTENCE_END = re.compile(r"[.!?][\"')\]]?$")
_CLAUSE_END = re.compile(r"[,;:][\"')\]]?$")


@dataclass
class WordCue:
    start: float
    end: float
    text: str
    probability: float | None = None


@dataclass
class PhraseCue:
    words: list[WordCue]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def text(self) -> str:
        return _join_words(self.words)


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _escape_ass(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def _join_word_texts(parts: list[str]) -> str:
    """Join Whisper word tokens without spaces before punctuation."""
    output = ""
    for raw in parts:
        token = _clean_text(raw)
        if not token:
            continue
        if not output:
            output = token
        elif re.match(r"^[,.;:!?%)}\]]", token):
            output += token
        elif output.endswith(("'", "’", "-", "—", "(")):
            output += token
        else:
            output += " " + token
    return output.strip()


def _join_words(words: list[WordCue]) -> str:
    return _join_word_texts([word.text for word in words])


def _plain_word(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9']+", "", value).lower()


def _natural_caption_text(text: str, style: str, content_type: str | None = None) -> str:
    """Add one intentional line break for dense clean/cinematic captions.

    libass can wrap automatically, but automatic wrapping often leaves articles or
    connectors stranded at the edge of a line. M5 chooses a balanced grammatical
    split so film/anime captions read like phrases rather than a word-count chunk.
    """
    clean = _clean_text(text)
    if style not in {"cinematic", "clean"}:
        return clean
    words = clean.split()
    if len(words) < 7 or len(clean) < 30:
        return clean

    cfg = _effective_style_config(style, content_type)
    # A little headroom below the total phrase cap keeps both rows visually compact.
    per_line_cap = max(20, min(32, int(cfg["max_chars"] * 0.68)))
    candidates: list[tuple[float, int]] = []
    for split in range(3, len(words) - 2):
        left = " ".join(words[:split])
        right = " ".join(words[split:])
        if len(left) > per_line_cap + 5 or len(right) > per_line_cap + 5:
            continue
        left_last = _plain_word(words[split - 1])
        right_first = _plain_word(words[split])
        score = abs(len(left) - len(right)) * 1.0
        if left_last in _WEAK_EDGE_WORDS:
            score += 24
        # Starting the second line with a contrast/consequence can be natural, while
        # starting it with an article/preposition usually looks machine-split.
        if right_first in {"a", "an", "the", "of", "to", "for", "with", "at", "from", "by", "as"}:
            score += 18
        if re.search(r"[,;:]$", words[split - 1]):
            score -= 8
        if right_first in {"but", "because", "so", "then", "when", "if", "however"}:
            score -= 4
        candidates.append((score, split))
    if not candidates:
        return clean
    _, split = min(candidates)
    left = " ".join(words[:split])
    right = " ".join(words[split:])
    return f"{left}\n{right}"


def _split_text(text: str, max_words: int, max_chars: int) -> list[str]:
    words = _clean_text(text).split()
    if not words:
        return []

    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and (len(current) >= max_words or len(candidate) > max_chars):
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _caption_position(
    style: str,
    layout: str,
    frame_size: str,
    width: int,
    height: int,
    caption_zone: str = "auto",
    platform: str = "auto",
    source_width: int = 0,
    source_height: int = 0,
    content_type: str = "auto",
) -> tuple[int, int]:
    """Place captions inside the picture and nudge them away from platform UI."""
    x = width // 2
    zone = (caption_zone or "auto").lower().strip()
    if zone not in {"upper", "middle", "lower"}:
        zone = "middle" if style in {"viral", "meme"} else "lower"

    ratios = {"upper": 0.34, "middle": 0.61, "lower": 0.85}
    ratio = ratios[zone]

    content = (content_type or "auto").lower().strip()
    anime_cinematic_lower = content == "anime" and style == "cinematic" and zone == "lower" and layout == "focus"
    if anime_cinematic_lower:
        # Anime's cinematic preset is intentionally anchored near the bottom edge of
        # the picture itself. 0.88 leaves enough room for two short lines while
        # keeping the text out of the visual centre.
        ratio = 0.88

    platform = (platform or "auto").lower().strip()
    # Lower captions are the ones most likely to collide with app chrome. Anime's
    # compact central window already leaves black canvas below it, so its Cinematic
    # captions can safely remain low inside the actual picture.
    if zone == "lower" and not anime_cinematic_lower:
        if platform == "tiktok":
            ratio = min(ratio, 0.77)
        elif platform == "shorts":
            ratio = min(ratio, 0.79)
        elif platform == "reels":
            ratio = min(ratio, 0.80)

    if layout in {"focus", "backdrop", "preserve"}:
        left, top, window_w, window_h = picture_window(
            layout, frame_size, source_width, source_height, width, height
        )
        # Keep the anchor centered inside the actual picture, not the black bars.
        return int(left + window_w / 2), int(top + window_h * ratio)

    return x, int(height * ratio)


def _cue_override(
    style: str,
    layout: str,
    frame_size: str,
    width: int,
    height: int,
    caption_zone: str = "auto",
    platform: str = "auto",
    source_width: int = 0,
    source_height: int = 0,
    content_type: str = "auto",
    *,
    phrase_transition: bool = True,
) -> str:
    x, y = _caption_position(
        style, layout, frame_size, width, height, caption_zone, platform, source_width, source_height, content_type
    )
    pos = fr"\an2\pos({x},{y})"
    if not phrase_transition:
        return "{" + pos + "}"
    if style == "viral":
        return "{" + pos + r"\fad(45,70)}"
    if style == "meme":
        return "{" + pos + r"\fad(35,60)}"
    if style == "cinematic":
        return "{" + pos + r"\fad(90,130)}"
    return "{" + pos + r"\fad(55,70)}"


def _style_line(style: str, content_type: str | None = None, width: int = 720) -> str:
    cfg = _effective_style_config(style, content_type)
    scale = max(0.55, min(1.0, width / 720.0))
    cfg["size"] = max(20, round(cfg["size"] * scale))
    cfg["outline"] = max(1, round(cfg["outline"] * scale))
    cfg["shadow"] = max(0, round(cfg["shadow"] * scale))
    return (
        "Style: Default,"
        f"{cfg['font']},{cfg['size']},{cfg['primary']},&H000000FF,&H00000000,&H78000000,"
        "-1,0,0,0,100,100,0,0,1,"
        f"{cfg['outline']},{cfg['shadow']},2,28,28,20,1"
    )


def _dedupe_words(words: list[TranscriptWord]) -> list[TranscriptWord]:
    seen: set[tuple[int, int, str]] = set()
    output: list[TranscriptWord] = []
    for word in sorted(words, key=lambda item: (item.start, item.end)):
        key = (round(word.start * 100), round(word.end * 100), word.text.lower())
        if key in seen:
            continue
        seen.add(key)
        output.append(word)
    return output


def _looks_like_bad_token(text: str, probability: float | None) -> bool:
    clean = re.sub(r"[^A-Za-z0-9']", "", text).lower()
    if not clean:
        return False
    if probability is not None and probability < 0.05 and len(clean) <= 2:
        return True
    if probability is not None and probability < 0.16 and clean in _FILLER_WORDS:
        return True
    return False


def _words_in_clip(
    segments: list[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    offset_seconds: float,
) -> list[WordCue]:
    raw_words: list[TranscriptWord] = []
    for segment in segments:
        if segment.end <= clip_start or segment.start >= clip_end:
            continue
        raw_words.extend(segment.words)

    cues: list[WordCue] = []
    for word in _dedupe_words(raw_words):
        absolute_start = max(float(word.start), clip_start)
        absolute_end = min(float(word.end), clip_end)
        if absolute_end <= absolute_start:
            continue
        text = _clean_text(word.text)
        if not text or _looks_like_bad_token(text, word.probability):
            continue
        start = max(0.0, absolute_start - clip_start + offset_seconds)
        end = min(max(clip_end - clip_start, 0.05), absolute_end - clip_start + offset_seconds)
        if end > start + 0.015:
            cues.append(WordCue(start=start, end=end, text=text, probability=word.probability))
    return cues


def _is_weak_edge(word: WordCue) -> bool:
    clean = re.sub(r"[^A-Za-z']", "", word.text).lower()
    return clean in _WEAK_EDGE_WORDS


def _rebalance_phrases(phrases: list[PhraseCue], max_words: int, max_chars: int) -> list[PhraseCue]:
    """Avoid ugly one-word leftovers and obvious connective fragments."""
    if len(phrases) <= 1:
        return phrases

    # Pull a dangling connective from the end of a phrase into the following one.
    for index in range(len(phrases) - 1):
        current = phrases[index]
        nxt = phrases[index + 1]
        if len(current.words) >= 2 and _is_weak_edge(current.words[-1]):
            candidate = [current.words[-1], *nxt.words]
            if len(candidate) <= max_words and len(_join_words(candidate)) <= max_chars:
                moved = current.words.pop()
                nxt.words.insert(0, moved)

    # Merge a tiny final fragment into the previous phrase when it still fits.
    if len(phrases) >= 2 and len(phrases[-1].words) <= 2:
        previous = phrases[-2]
        tail = phrases[-1]
        candidate = [*previous.words, *tail.words]
        if len(candidate) <= max_words + 2 and len(_join_words(candidate)) <= max_chars + 8:
            phrases[-2] = PhraseCue(candidate)
            phrases.pop()

    return [phrase for phrase in phrases if phrase.words]


def _make_phrases(words: list[WordCue], style: str, content_type: str | None = None) -> list[PhraseCue]:
    if not words:
        return []

    cfg = _effective_style_config(style, content_type)
    max_words = int(cfg["max_words"])
    max_chars = int(cfg["max_chars"])
    max_duration = float(cfg["max_duration"])
    pause_break = float(cfg["pause_break"])

    phrases: list[PhraseCue] = []
    current: list[WordCue] = []
    for word in words:
        previous = current[-1] if current else None
        candidate = [*current, word]
        candidate_text = _join_words(candidate)
        long_pause = previous is not None and word.start - previous.end > pause_break
        sentence_break = previous is not None and bool(_SENTENCE_END.search(previous.text))
        clause_break = (
            previous is not None
            and bool(_CLAUSE_END.search(previous.text))
            and word.start - previous.end > 0.20
            and len(current) >= 3
        )
        too_large = bool(current) and (len(candidate) > max_words or len(candidate_text) > max_chars)
        too_long = bool(current) and (word.end - current[0].start > max_duration)

        if current and (long_pause or sentence_break or clause_break or too_large or too_long):
            phrases.append(PhraseCue(words=current))
            current = [word]
        else:
            current.append(word)

    if current:
        phrases.append(PhraseCue(words=current))

    return _rebalance_phrases(phrases, max_words, max_chars)


def _styled_phrase_text(
    phrase: PhraseCue, active_index: int, style: str, content_type: str | None = None
) -> str:
    cfg = _effective_style_config(style, content_type)
    output: list[str] = []
    for index, word in enumerate(phrase.words):
        text = _escape_ass(word.text.upper() if style == "meme" else word.text)
        if index == active_index:
            text = (
                r"{\c" + str(cfg["active"])
                + r"\bord6\shad2\fscx100\fscy100"
                + r"\t(0,75,\fscx108\fscy108)\t(75,150,\fscx103\fscy103)}"
                + text
                + r"{\c" + str(cfg["primary"])
                + r"\bord5\shad2\fscx100\fscy100}"
            )
        output.append(text)
    # Joining ASS-decorated tokens with spaces is safe because punctuation normally
    # arrives attached to the word token from faster-whisper.
    return " ".join(output)


def _fallback_segment_cues(
    segments: list[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    *,
    max_words: int,
    max_chars: int,
    offset_seconds: float,
) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    clip_duration = max(clip_end - clip_start, 0.05)
    for segment in segments:
        overlap_start = max(float(segment.start), clip_start)
        overlap_end = min(float(segment.end), clip_end)
        if overlap_end <= overlap_start:
            continue
        chunks = _split_text(segment.text, max_words=max_words, max_chars=max_chars)
        if not chunks:
            continue
        relative_start = max(0.0, overlap_start - clip_start + offset_seconds)
        relative_end = min(clip_duration, overlap_end - clip_start + offset_seconds)
        if relative_end <= relative_start:
            continue
        step = max(relative_end - relative_start, 0.2) / len(chunks)
        for index, text in enumerate(chunks):
            cue_start = relative_start + index * step
            cue_end = min(relative_start + (index + 1) * step, clip_duration)
            if cue_end > cue_start + 0.03:
                cues.append((cue_start, cue_end, text))
    return cues


def write_clip_ass(
    segments: list[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    output_path: str,
    *,
    caption_style: str = "clean",
    layout_mode: str = "fill",
    frame_size: str = "balanced",
    width: int = 720,
    height: int = 1280,
    caption_offset_ms: int = 0,
    caption_zone: str = "auto",
    platform: str = "auto",
    content_type: str = "auto",
    source_width: int = 0,
    source_height: int = 0,
) -> tuple[str, bool]:
    """Write readable in-frame ASS captions with exact word timing when available."""
    style = caption_style if caption_style in STYLE_CONFIG else "clean"
    frame_size = normalize_frame_size(frame_size)
    cfg = _effective_style_config(style, content_type)
    offset_seconds = caption_offset_ms / 1000.0

    words = _words_in_clip(segments, clip_start, clip_end, offset_seconds)
    phrases = _make_phrases(words, style, content_type)
    word_timed = bool(phrases)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
{_style_line(style, content_type, width)}

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header.rstrip()]
    phrase_override = _cue_override(
        style, layout_mode, frame_size, width, height, caption_zone, platform,
        source_width, source_height, content_type, phrase_transition=True
    )
    stable_override = _cue_override(
        style, layout_mode, frame_size, width, height, caption_zone, platform,
        source_width, source_height, content_type, phrase_transition=False
    )

    if word_timed:
        for phrase in phrases:
            if style in {"viral", "meme"}:
                for index, word in enumerate(phrase.words):
                    cue_start = word.start
                    if index + 1 < len(phrase.words):
                        cue_end = max(phrase.words[index + 1].start, cue_start + 0.05)
                    else:
                        cue_end = max(phrase.end, cue_start + 0.05)
                    display = _styled_phrase_text(phrase, index, style, content_type)
                    lines.append(
                        f"Dialogue: 0,{_ass_time(cue_start)},{_ass_time(cue_end)},Default,,0,0,0,,{stable_override}{display}"
                    )
            else:
                display = _escape_ass(_natural_caption_text(phrase.text, style, content_type))
                lines.append(
                    f"Dialogue: 0,{_ass_time(phrase.start)},{_ass_time(max(phrase.end, phrase.start + 0.05))},Default,,0,0,0,,{phrase_override}{display}"
                )
    else:
        fallback = _fallback_segment_cues(
            segments,
            clip_start,
            clip_end,
            max_words=int(cfg["max_words"]),
            max_chars=int(cfg["max_chars"]),
            offset_seconds=offset_seconds,
        )
        if not fallback:
            fallback = [(0.0, min(max(clip_end - clip_start, 0.5), 1.0), " ")]
        for start, end, text in fallback:
            if style == "meme":
                display_text = text.upper()
            else:
                display_text = _natural_caption_text(text, style, content_type)
            display = _escape_ass(display_text)
            lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(max(end, start + 0.05))},Default,,0,0,0,,{phrase_override}{display}"
            )

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return str(target), word_timed
