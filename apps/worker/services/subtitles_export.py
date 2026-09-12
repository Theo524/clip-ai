from __future__ import annotations

from typing import Iterable


def _srt_time(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, millis = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def _vtt_time(seconds: float) -> str:
    return _srt_time(seconds).replace(",", ".")


def segments_for_range(segments: Iterable, start: float, end: float):
    for segment in segments:
        seg_start = max(float(segment.start), start)
        seg_end = min(float(segment.end), end)
        if seg_end <= seg_start:
            continue
        text = str(segment.text).strip()
        if not text:
            continue
        yield seg_start - start, seg_end - start, text


def to_srt(segments: Iterable, start: float, end: float) -> str:
    blocks = []
    for idx, (a, b, text) in enumerate(segments_for_range(segments, start, end), start=1):
        blocks.append(f"{idx}\n{_srt_time(a)} --> {_srt_time(b)}\n{text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def to_vtt(segments: Iterable, start: float, end: float) -> str:
    blocks = ["WEBVTT\n"]
    for a, b, text in segments_for_range(segments, start, end):
        blocks.append(f"{_vtt_time(a)} --> {_vtt_time(b)}\n{text}\n")
    return "\n".join(blocks)
