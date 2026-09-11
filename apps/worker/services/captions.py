from dataclasses import dataclass
from pathlib import Path
import re

from models import TranscriptSegment, TranscriptWord
from services.layouts import content_window, normalize_frame_size


STYLE_CONFIG = {
    "viral": {
        "font": "Trebuchet MS",
        "size": 58,
        "max_words": 4,
        "max_chars": 28,
        "primary": "&H00FFFFFF",
        "active": "&H0048E8FF",  # warm yellow in ASS BGR order
        "outline": 5,
        "shadow": 2,
    },
    "cinematic": {
        "font": "Segoe UI Semibold",
        "size": 38,
        "max_words": 8,
        "max_chars": 46,
        "primary": "&H00FFFFFF",
        "active": "&H00FFFFFF",
        "outline": 2,
        "shadow": 1,
    },
    "clean": {
        "font": "Arial",
        "size": 44,
        "max_words": 7,
        "max_chars": 40,
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
        "primary": "&H00FFFFFF",
        "active": "&H0000D7FF",  # orange/yellow accent
        "outline": 5,
        "shadow": 1,
    },
}


@dataclass
class WordCue:
    start: float
    end: float
    text: str


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
    def text(self) -> str:
        return " ".join(word.text for word in self.words)


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
) -> tuple[int, int]:
    """Place every caption inside the actual picture area, never in margins."""
    x = width // 2
    zone = (caption_zone or "auto").lower().strip()
    if zone not in {"upper", "middle", "lower"}:
        if style in {"viral", "meme"}:
            zone = "middle"
        else:
            zone = "lower"

    # These ratios are relative to the *picture* rather than the 9:16 canvas.
    # Cinematic lower captions stay safely inside the picture instead of drifting
    # into the dark Focus margins.
    ratios = {
        "upper": 0.34,
        "middle": 0.62,
        "lower": 0.85,
    }
    ratio = ratios[zone]

    if layout in {"focus", "backdrop"}:
        _wx, top, _ww, window_h = content_window(frame_size, width, height)
        y = int(top + window_h * ratio)
        return x, y

    return x, int(height * ratio)


def _cue_override(
    style: str,
    layout: str,
    frame_size: str,
    width: int,
    height: int,
    caption_zone: str = "auto",
    *,
    phrase_transition: bool = True,
) -> str:
    x, y = _caption_position(style, layout, frame_size, width, height, caption_zone)
    pos = fr"\an2\pos({x},{y})"
    # Phrase-level entry/exit only. Word changes never restart these transitions.
    if not phrase_transition:
        if style in {"viral", "meme"}:
            # Move only the active-word overlay a few pixels upward. The stable
            # base phrase never moves, so this reads as a word pop without layout
            # jitter or a full-caption re-entry.
            return "{" + fr"\an2\move({x},{y + 6},{x},{y},0,95)" + "}"
        return "{" + pos + "}"
    if style == "viral":
        return "{" + pos + r"\fad(45,70)}"
    if style == "meme":
        return "{" + pos + r"\fad(35,60)}"
    if style == "cinematic":
        return "{" + pos + r"\fad(90,130)}"
    return "{" + pos + r"\fad(55,70)}"

def _style_line(style: str) -> str:
    cfg = STYLE_CONFIG[style]
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
        if not text:
            continue
        start = absolute_start - clip_start + offset_seconds
        end = absolute_end - clip_start + offset_seconds
        # An offset can push the first/last word outside the cut; clamp rather than
        # dropping all following timing information.
        start = max(0.0, start)
        end = min(max(clip_end - clip_start, 0.05), end)
        if end > start + 0.015:
            cues.append(WordCue(start=start, end=end, text=text))
    return cues


def _make_phrases(words: list[WordCue], max_words: int, max_chars: int) -> list[PhraseCue]:
    if not words:
        return []

    phrases: list[PhraseCue] = []
    current: list[WordCue] = []
    for word in words:
        candidate_text = " ".join([*(item.text for item in current), word.text])
        previous = current[-1] if current else None
        long_pause = previous is not None and word.start - previous.end > 0.55
        sentence_break = previous is not None and bool(re.search(r"[.!?][\"')\]]?$", previous.text))
        too_large = bool(current) and (len(current) >= max_words or len(candidate_text) > max_chars)

        if current and (long_pause or sentence_break or too_large):
            phrases.append(PhraseCue(words=current))
            current = [word]
        else:
            current.append(word)

    if current:
        phrases.append(PhraseCue(words=current))
    return phrases


def _base_phrase_text(phrase: PhraseCue, style: str) -> str:
    return " ".join(
        _escape_ass(word.text.upper() if style == "meme" else word.text)
        for word in phrase.words
    )


def _active_word_overlay_text(phrase: PhraseCue, active_index: int, style: str) -> str:
    """Render only the active word while preserving the phrase's text layout.

    Non-active words are fully transparent but remain in the line, so the accent
    word lands over the stable base phrase instead of redrawing/fading the whole
    caption block every time Whisper advances to the next word.
    """
    cfg = STYLE_CONFIG[style]
    output: list[str] = []
    for index, word in enumerate(phrase.words):
        text = _escape_ass(word.text.upper() if style == "meme" else word.text)
        if index == active_index:
            # Colour/outline emphasis does not change word width, so the active
            # overlay stays perfectly aligned with the persistent base phrase.
            text = (
                r"{\alpha&H00&\c" + str(cfg["active"])
                + r"\bord6\shad2}"
                + text
                + r"{\alpha&HFF&\c" + str(cfg["primary"]) + r"\bord5\shad2}"
            )
        else:
            text = r"{\alpha&HFF&}" + text
        output.append(text)
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
    """Compatibility path for jobs created before Milestone 8."""
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
) -> tuple[str, bool]:
    """Write in-frame ASS captions using exact word timing when available.

    Returns ``(path, word_timed)`` so the API/UI can report whether the freshly
    analysed transcript supplied real word timestamps or used the legacy fallback.
    """
    style = caption_style if caption_style in STYLE_CONFIG else "clean"
    frame_size = normalize_frame_size(frame_size)
    cfg = STYLE_CONFIG[style]
    offset_seconds = caption_offset_ms / 1000.0

    words = _words_in_clip(segments, clip_start, clip_end, offset_seconds)
    phrases = _make_phrases(words, int(cfg["max_words"]), int(cfg["max_chars"]))
    word_timed = bool(phrases)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
{_style_line(style)}

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header.rstrip()]
    phrase_override = _cue_override(
        style, layout_mode, frame_size, width, height, caption_zone, phrase_transition=True
    )
    active_override = _cue_override(
        style, layout_mode, frame_size, width, height, caption_zone, phrase_transition=False
    )

    if word_timed:
        for phrase in phrases:
            if style in {"viral", "meme"}:
                # Layer 0: one stable phrase event for the whole phrase lifetime.
                # Layer 1: a transparent-layout overlay that reveals/pops only the
                # currently spoken word. Word changes therefore never fade/re-enter
                # the full caption block.
                base_display = _base_phrase_text(phrase, style)
                lines.append(
                    f"Dialogue: 0,{_ass_time(phrase.start)},{_ass_time(max(phrase.end, phrase.start + 0.05))},Default,,0,0,0,,{phrase_override}{base_display}"
                )
                for index, word in enumerate(phrase.words):
                    cue_start = word.start
                    cue_end = max(word.end, cue_start + 0.05)
                    display = _active_word_overlay_text(phrase, index, style)
                    lines.append(
                        f"Dialogue: 1,{_ass_time(cue_start)},{_ass_time(cue_end)},Default,,0,0,0,,{active_override}{display}"
                    )
            else:
                display = _escape_ass(phrase.text)
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
            display = _escape_ass(text.upper() if style == "meme" else text)
            lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(max(end, start + 0.05))},Default,,0,0,0,,{phrase_override}{display}"
            )

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return str(target), word_timed
