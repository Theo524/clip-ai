from pathlib import Path
import re

from models import TranscriptSegment
from services.layouts import content_window, normalize_frame_size


STYLE_CONFIG = {
    "viral": {
        "font": "Trebuchet MS",
        "size": 58,
        "max_words": 4,
        "max_chars": 28,
        "primary": "&H00FFFFFF",
        "outline": 5,
        "shadow": 2,
    },
    "cinematic": {
        "font": "Segoe UI Semibold",
        "size": 38,
        "max_words": 8,
        "max_chars": 46,
        "primary": "&H00FFFFFF",
        "outline": 2,
        "shadow": 1,
    },
    "clean": {
        "font": "Arial",
        "size": 44,
        "max_words": 7,
        "max_chars": 40,
        "primary": "&H00FFFFFF",
        "outline": 3,
        "shadow": 1,
    },
    "meme": {
        "font": "Impact",
        "size": 54,
        "max_words": 5,
        "max_chars": 32,
        "primary": "&H00FFFFFF",
        "outline": 5,
        "shadow": 1,
    },
}


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


def _highlight_keyword(text: str) -> str:
    words = text.split()
    if len(words) < 2:
        return _escape_ass(text)

    candidates = [
        (index, re.sub(r"[^A-Za-z0-9£$%'-]", "", word))
        for index, word in enumerate(words)
    ]
    index, cleaned = max(candidates, key=lambda item: len(item[1]))
    if len(cleaned) < 4:
        return _escape_ass(text)

    escaped = [_escape_ass(word) for word in words]
    escaped[index] = r"{\c&H0048E8FF&}" + escaped[index] + r"{\c&H00FFFFFF&}"
    return " ".join(escaped)


def _caption_position(style: str, layout: str, frame_size: str, width: int, height: int) -> tuple[int, int]:
    """Place every caption inside the actual picture area, never in margins."""
    x = width // 2

    if layout in {"focus", "backdrop"}:
        _wx, top, _ww, window_h = content_window(frame_size, width, height)
        if style == "cinematic":
            # Traditional lower-picture placement, but still comfortably inside the image.
            y = int(top + window_h * 0.88)
        elif style in {"viral", "meme"}:
            y = int(top + window_h * 0.68)
        else:
            y = int(top + window_h * 0.80)
        return x, y

    if layout == "fill":
        if style in {"viral", "meme"}:
            return x, int(height * 0.66)
        if style == "cinematic":
            return x, int(height * 0.88)
        return x, int(height * 0.80)

    # Preserve is only selected for already-vertical footage, so the picture occupies
    # almost the whole canvas; keep the captions comfortably inside that picture.
    if style in {"viral", "meme"}:
        return x, int(height * 0.68)
    if style == "cinematic":
        return x, int(height * 0.87)
    return x, int(height * 0.80)


def _cue_override(style: str, layout: str, frame_size: str, width: int, height: int) -> str:
    x, y = _caption_position(style, layout, frame_size, width, height)
    pos = fr"\an2\pos({x},{y})"
    if style == "viral":
        return "{" + pos + r"\fscx84\fscy84\t(0,120,\fscx108\fscy108)\t(120,240,\fscx100\fscy100)}"
    if style == "meme":
        return "{" + pos + r"\fad(60,80)\fscx92\fscy92\t(0,130,\fscx104\fscy104)}"
    if style == "cinematic":
        return "{" + pos + r"\fad(120,170)}"
    return "{" + pos + r"\fad(70,90)}"


def _style_line(style: str) -> str:
    cfg = STYLE_CONFIG[style]
    return (
        "Style: Default,"
        f"{cfg['font']},{cfg['size']},{cfg['primary']},&H000000FF,&H00000000,&H78000000,"
        "-1,0,0,0,100,100,0,0,1,"
        f"{cfg['outline']},{cfg['shadow']},2,28,28,20,1"
    )


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
) -> str:
    """Write ASS captions that always sit on top of the actual video picture."""
    style = caption_style if caption_style in STYLE_CONFIG else "clean"
    frame_size = normalize_frame_size(frame_size)
    cfg = STYLE_CONFIG[style]
    cues: list[tuple[float, float, str]] = []

    for segment in segments:
        overlap_start = max(float(segment.start), clip_start)
        overlap_end = min(float(segment.end), clip_end)
        if overlap_end <= overlap_start:
            continue

        chunks = _split_text(
            segment.text,
            max_words=int(cfg["max_words"]),
            max_chars=int(cfg["max_chars"]),
        )
        if not chunks:
            continue

        relative_start = overlap_start - clip_start
        relative_end = overlap_end - clip_start
        span = max(relative_end - relative_start, 0.55)
        step = span / len(chunks)

        for index, text in enumerate(chunks):
            cue_start = relative_start + index * step
            cue_end = min(relative_start + (index + 1) * step, clip_end - clip_start)
            if cue_end - cue_start < 0.12:
                continue
            cues.append((cue_start, cue_end, text))

    if not cues:
        cues.append((0.0, min(max(clip_end - clip_start, 0.5), 1.0), " "))

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
    for start, end, text in cues:
        if style == "viral":
            display = _highlight_keyword(text)
        elif style == "meme":
            display = _escape_ass(text.upper())
        else:
            display = _escape_ass(text)
        override = _cue_override(style, layout_mode, frame_size, width, height)
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(max(end, start + 0.05))},Default,,0,0,0,,{override}{display}"
        )

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return str(target)
