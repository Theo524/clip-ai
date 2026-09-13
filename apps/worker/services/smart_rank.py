"""Transcript-first M2 clip selection; no new model downloads or render changes."""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_left, bisect_right
import re
import subprocess

from models import ClipCandidate, TranscriptSegment
from services.context import ContentContext, _topic_tokens
from services.copywriter import generate_clip_copy_local
from services.local_rank import (
    HOOK_PHRASES, PAYOFF_PHRASES, PIVOT_PHRASES, TRAILING_DEPENDENCIES,
    _candidate_score, _clean, _first_sentence, _starts_clean, _too_similar, _words,
)


# These are soft limits. A sentence/payoff may extend beyond the usual range.
DURATION_GUIDES = {
    "meme-comedy": (8, 30), "anime": (15, 45), "film-tv": (15, 45),
    "podcast": (20, 60), "documentary": (25, 75), "gameplay": (15, 50),
    "other": (12, 60),
}
RANKING_VERSION = "m2.1"


@dataclass(frozen=True)
class Scene:
    first: int
    last: int
    boundary: str


def detect_shot_boundaries(media_path: str, *, timeout: int = 35) -> list[float]:
    """Sample keyframes at thumbnail size. Failure never blocks local analysis.

    A cut is only used as a scene boundary when transcript evidence also agrees;
    ordinary dialogue shot/reverse-shot edits must remain one coherent moment.
    """
    command = [
        "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info", "-threads", "2",
        "-skip_frame", "nokey", "-i", media_path, "-an",
        "-vf", "scale=128:-2,select=gt(scene\\,0.30),showinfo", "-f", "null", "-",
    ]
    try:
        output = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if output.returncode:
        return []
    return [float(value) for value in re.findall(r"showinfo.*?pts_time:\s*([\d.]+)", output.stderr)[:3000]]


def _topic_shift(segments: list[TranscriptSegment], index: int) -> bool:
    left = _topic_tokens(" ".join(s.text for s in segments[max(0, index - 4):index]))
    right = _topic_tokens(" ".join(s.text for s in segments[index:min(len(segments), index + 4)]))
    return len(left) >= 3 and len(right) >= 3 and len(left & right) / len(left | right) < 0.09


def segment_scenes(segments: list[TranscriptSegment], context: ContentContext,
                   shot_boundaries: list[float] | tuple[float, ...] = ()) -> list[Scene]:
    if not segments:
        return []
    scenes: list[Scene] = []
    first = 0
    for index in range(1, len(segments)):
        current, previous = segments[index], segments[index - 1]
        gap = max(0.0, current.start - previous.end)
        shift = _topic_shift(segments, index)
        cue = bool(re.search(r"\b(next (clip|one|scene)|meanwhile|back to)\b", current.text.lower()))
        shot = any(abs(current.start - time) <= 1.5 for time in shot_boundaries)
        compilation = context.resolved_structure == "compilation"
        reason = ""
        if gap >= (2.2 if compilation else 3.5):
            reason = "long pause"
        elif compilation and (cue or (gap >= 0.8 and shift)):
            reason = "local topic change"
        elif gap >= 1.2 and shift:
            reason = "topic change"
        elif shot and gap >= 0.5 and (shift or gap >= 1.2):
            reason = "shot change"
        if reason:
            scenes.append(Scene(first, index - 1, reason))
            first = index
    scenes.append(Scene(first, len(segments) - 1, "end of source"))
    return scenes


def _unfinished(text: str) -> bool:
    clean = _clean(text).rstrip('"”’ ')
    words = _words(clean[-90:])
    if not words:
        return True
    if words[-1] in TRAILING_DEPENDENCIES:
        return True
    # Whisper sometimes punctuates an incomplete thought. Check the words too.
    return bool(re.search(r"\b(and then|the reason (is|was)|what happened (is|was))\W*$", clean.lower()))


def _confidence(segments: list[TranscriptSegment]) -> float | None:
    probabilities = [w.probability for seg in segments for w in seg.words if w.probability is not None]
    return sum(probabilities) / len(probabilities) if len(probabilities) >= 4 else None


def _moment_type(text: str) -> str:
    lower = text.lower()
    cues = {
        "funny": ("joke", "funny", "laugh", "hilarious", "punchline"),
        "emotional": ("cried", "heartbroken", "love", "miss you", "goodbye"),
        "action": ("fight", "attack", "escape", "battle", "explosion"),
        "reveal": ("turns out", "the truth", "secret", "actually", "revealed"),
        "argument": ("disagree", "you're wrong", "but you", "debate"),
        "reaction": ("no way", "oh my", "what?", "unbelievable"),
        "informative": ("because", "the reason", "how to", "for example"),
    }
    return next((name for name, phrases in cues.items() if any(p in lower for p in phrases)), "unknown")


def _ending_quality(segment: TranscriptSegment, next_segment: TranscriptSegment | None) -> int:
    if _unfinished(segment.text):
        return -1
    clean = _clean(segment.text)
    pause = max(0.0, next_segment.start - segment.end) if next_segment else 10.0
    if clean.endswith((".", "!", "?", "…")):
        return 2
    return 1 if pause >= 0.6 or next_segment is None else 0


def rank_clip_candidates_m2(segments: list[TranscriptSegment], max_clips: int,
                            context: ContentContext, *, shot_boundaries: list[float] | tuple[float, ...] = ()) -> list[ClipCandidate]:
    if not segments or max_clips < 1:
        return []
    scenes = segment_scenes(segments, context, shot_boundaries)
    shot_times = sorted(shot_boundaries)
    low, high = DURATION_GUIDES.get(context.resolved_type, DURATION_GUIDES["other"])
    candidates: list[tuple[ClipCandidate, int, str]] = []
    for scene_id, scene in enumerate(scenes):
        scene_start, scene_end = segments[scene.first].start, segments[scene.last].end
        for start_index in range(scene.first, scene.last + 1):
            start_seg = segments[start_index]
            preceding = segments[start_index - 1] if start_index > scene.first else None
            if not _starts_clean(start_seg.text) and preceding and start_index > scene.first + 2:
                continue
            # Keep generation bounded on long transcripts; no global quadratic scan.
            text_parts: list[str] = []
            for end_index in range(start_index, min(scene.last + 1, start_index + 38)):
                end_seg = segments[end_index]
                duration = end_seg.end - start_seg.start
                if duration > min(95, high + 20):
                    break
                text_parts.append(end_seg.text)
                if duration < max(5.0, low - 5):
                    continue
                following = segments[end_index + 1] if end_index < scene.last else None
                ending_quality = _ending_quality(end_seg, following)
                if ending_quality < 1:
                    continue
                # A question isn't an ending if the answer immediately follows.
                if end_seg.text.rstrip().endswith("?") and following and following.start - end_seg.end < 2.0:
                    continue
                text = _clean(" ".join(text_parts))
                if len(_words(text)) < 9 and duration > 15:
                    continue
                gap_before = start_seg.start - preceding.end if preceding else 10.0
                gap_after = following.start - end_seg.end if following else 10.0
                old_score, reasons, breakdown, note = _candidate_score(
                    text, duration, start_seg.text, end_seg.text, gap_before, gap_after)
                complete_start = _starts_clean(start_seg.text) or start_index == scene.first
                payoff = any(phrase in text.lower() for phrase in PAYOFF_PHRASES)
                turn = any(phrase in text.lower() for phrase in PIVOT_PHRASES)
                story = min(98, 40 + (18 if complete_start else 0) + 20 * ending_quality // 2
                            + (12 if payoff else 0) + (8 if turn else 0))
                hook = any(phrase in start_seg.text.lower()[:110] for phrase in HOOK_PHRASES)
                # The old length reward must not force every result into 24–48 s.
                old_length_bias = 15 if 24 <= duration <= 48 else 8 if 18 <= duration <= 60 else -min(18, abs(duration - 36) * .65)
                score = 0.42 * (old_score - old_length_bias * .62) + 0.58 * (
                    breakdown["Hook"] * .20 + breakdown["Standalone"] * .18
                    + breakdown["Payoff"] * .22 + breakdown["Clarity"] * .12 + story * .28)
                if duration < low:
                    score -= min(10, (low - duration) * .8)
                elif duration > high:
                    score -= min(9, (duration - high) * .45)
                if not complete_start:
                    score -= 10
                if ending_quality == 1:
                    score -= 8
                if payoff:
                    reasons = ["Complete payoff or takeaway", *reasons]
                if hook:
                    reasons = ["Strong opening hook", *reasons]
                warnings = []
                if ending_quality == 1:
                    warnings.append("Ending boundary is uncertain")
                if not complete_start:
                    warnings.append("Opening may need more context")
                if not payoff and not turn:
                    warnings.append("Story completeness may be limited")
                confidence = _confidence(segments[start_index:end_index + 1])
                if confidence is not None and confidence < .55:
                    warnings.append("Low transcript confidence")
                    score -= 9
                cuts = bisect_right(shot_times, end_seg.end) - bisect_left(shot_times, start_seg.start)
                if shot_times:
                    visual_score = max(35, 78 - max(0, round(cuts / max(duration, 1) * 90) - 20))
                    breakdown["Visual"] = visual_score
                    if cuts >= 5 and cuts / max(duration, 1) > .38:
                        warnings.append("Frequent shot changes: review framing")
                        score -= 4
                clip = ClipCandidate(
                    start=round(max(scene_start, start_seg.start - .12), 2),
                    end=round(min(scene_end + .16, end_seg.end + .16), 2),
                    title="", social_caption="",
                    hook=_first_sentence(text), score=max(1, min(98, round(score))),
                    reasons=list(dict.fromkeys(reasons))[:4] or ["Complete local moment"],
                    score_breakdown={**breakdown, "Story": story}, editor_note=note,
                    context={"moment_type": _moment_type(text), "scene_id": scene_id,
                             "scene_start": round(scene_start, 3), "scene_end": round(scene_end, 3),
                             "quality_warnings": warnings, "shot_changes": cuts if shot_times else None,
                             "transcript_confidence": round(confidence, 3) if confidence is not None else None},
                )
                candidates.append((clip, scene_id, text))
    # If a short scene has no admissible range, return its best complete span.
    if not candidates:
        scene = max(scenes, key=lambda item: segments[item.last].end - segments[item.first].start)
        first_start = segments[scene.first].start
        last_index = scene.first
        for index in range(scene.first + 1, scene.last + 1):
            if segments[index].end - first_start > 90:
                break
            last_index = index
        text = _clean(" ".join(s.text for s in segments[scene.first:last_index + 1]))
        generated = generate_clip_copy_local(text, "auto")
        last = segments[last_index]
        warning = ["Ending may feel abrupt"] if _unfinished(last.text) or last_index < scene.last else []
        return [ClipCandidate(start=max(0, first_start - .12), end=min(last.end + .16, first_start + 175),
                              title=generated.title, social_caption=generated.social_caption,
                              hook=_first_sentence(text), score=40 if warning else 60,
                              reasons=["Best available local moment"],
                              context={"moment_type": _moment_type(text), "scene_id": scenes.index(scene),
                                       "scene_start": first_start, "scene_end": last.end,
                                       "quality_warnings": warning})]
    candidates.sort(key=lambda item: (item[0].score, -(item[0].end - item[0].start)), reverse=True)
    selected: list[tuple[ClipCandidate, int, str]] = []
    # First three favor distinct scenes when their quality is reasonably close.
    diverse_scenes = {scene_id for clip, scene_id, _ in candidates if clip.score >= candidates[0][0].score - 15}
    for clip, scene_id, text in candidates:
        if len(selected) >= min(3, max_clips):
            break
        chosen_scenes = {item[1] for item in selected}
        if scene_id in chosen_scenes and diverse_scenes - chosen_scenes:
            continue
        if not any(_too_similar(clip, item[0]) for item in selected):
            selected.append((clip, scene_id, text))
    for clip, scene_id, text in candidates:
        if len(selected) >= max_clips:
            break
        if any(_too_similar(clip, item[0]) or
               (scene_id == item[1] and abs(clip.start - item[0].start) < 15) for item in selected):
            continue
        selected.append((clip, scene_id, text))
    for clip, _, text in selected:
        generated = generate_clip_copy_local(text, "auto")
        clip.title, clip.social_caption = generated.title, generated.social_caption
    return [clip for clip, _, _ in selected]
