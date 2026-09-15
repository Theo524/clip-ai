from __future__ import annotations

from models import TranscriptSegment, TranscriptWord


def _interpolate(values: list[float], position: float) -> float:
    if not values:
        return 0.0
    if position <= 0:
        return values[0]
    last = len(values) - 1
    if position >= last:
        return values[last]
    left = int(position)
    right = min(last, left + 1)
    fraction = position - left
    return values[left] * (1.0 - fraction) + values[right] * fraction


def corrected_segment_with_preserved_timing(
    original_segments: list[TranscriptSegment],
    start: float,
    end: float,
    text: str,
) -> TranscriptSegment | None:
    """Create an edited transcript segment while preserving the original speech rhythm.

    Earlier versions spread corrected text evenly across the entire selected clip. A one-word
    typo fix could therefore make every following caption appear too early or too late. This
    helper reuses exact word timestamps when counts match and otherwise resamples the original
    word-boundary timeline, including pauses, across the corrected tokens.
    """
    cleaned = " ".join((text or "").split())
    tokens = cleaned.split()
    if not tokens:
        return None

    original_words: list[TranscriptWord] = []
    for segment in original_segments:
        if segment.end < start or segment.start > end:
            continue
        for word in segment.words:
            if word.end <= start or word.start >= end:
                continue
            original_words.append(word)
    original_words.sort(key=lambda item: (item.start, item.end))

    if original_words and len(original_words) == len(tokens):
        new_words = [
            TranscriptWord(
                start=max(start, float(old.start)),
                end=min(end, float(old.end)),
                text=token,
                probability=old.probability,
            )
            for old, token in zip(original_words, tokens)
        ]
        seg_start = max(start, new_words[0].start)
        seg_end = min(end, new_words[-1].end)
        return TranscriptSegment(start=seg_start, end=max(seg_start + 0.05, seg_end), text=cleaned, words=new_words)

    if original_words:
        # Build boundaries halfway through real gaps so resampling preserves the cadence.
        boundaries = [max(start, float(original_words[0].start))]
        for left, right in zip(original_words, original_words[1:]):
            left_end = min(end, float(left.end))
            right_start = max(start, float(right.start))
            boundaries.append(max(boundaries[-1], (left_end + right_start) / 2.0))
        boundaries.append(min(end, float(original_words[-1].end)))
        if boundaries[-1] <= boundaries[0]:
            boundaries = [start, end]

        old_count = max(1, len(original_words))
        new_count = len(tokens)
        new_words: list[TranscriptWord] = []
        for index, token in enumerate(tokens):
            a_pos = (index / new_count) * old_count
            b_pos = ((index + 1) / new_count) * old_count
            a = _interpolate(boundaries, a_pos)
            b = _interpolate(boundaries, b_pos)
            if b <= a:
                b = min(end, a + 0.05)
            new_words.append(TranscriptWord(start=a, end=b, text=token, probability=None))
        return TranscriptSegment(
            start=new_words[0].start,
            end=max(new_words[0].start + 0.05, new_words[-1].end),
            text=cleaned,
            words=new_words,
        )

    duration = max(0.1, end - start)
    new_words = []
    for index, token in enumerate(tokens):
        a = start + duration * (index / len(tokens))
        b = start + duration * ((index + 1) / len(tokens))
        new_words.append(TranscriptWord(start=a, end=b, text=token, probability=None))
    return TranscriptSegment(start=start, end=end, text=cleaned, words=new_words)
