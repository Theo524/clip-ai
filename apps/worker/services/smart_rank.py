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
RANKING_VERSION = "v23-quality-v3"


NARRATIVE_CLOSURE_CUES = tuple(dict.fromkeys((*PAYOFF_PHRASES,
    "finally", "ultimately", "therefore", "that was it", "that's the point",
    "that is the point", "in other words", "so the answer", "which is why",
)))

NARRATIVE_CLOSURE_PATTERNS = (
    r"\bthat (?:was|is) (?:the )?(?:proof|answer|reason|result|solution|point)\b[^.!?]{0,90}[.!?]?",
    r"\bthis (?:was|is) (?:the )?(?:proof|answer|reason|result|solution|point)\b[^.!?]{0,90}[.!?]?",
)

STRONG_CONTINUATION_STARTS = (
    "because ", "that's because", "that is because", "the answer ", "the reason ",
    "that's why", "that is why", "turns out", "which means", "which is why",
    "and then", "but then", "however", "until ", "eventually", "finally",
)

RESPONSE_STARTS = (
    "yes ", "no ", "yeah ", "exactly", "right ", "because ", "that's because",
    "that is because", "of course", "not really", "actually ",
)

# Short reactions can be the emotional/comedic payoff of a scene. They are only
# treated as required continuation when they are immediate and scene-local.
REACTION_STARTS = (
    "no way", "what?", "wait", "seriously", "oh no", "oh my", "wow",
    "unbelievable", "i can't believe", "i cannot believe", "you're kidding",
    "you are kidding", "that's crazy", "that is crazy", "damn", "whoa",
)

OPEN_LOOP_PATTERNS = (
    r"\bthe reason (?:is|was)?\s*$",
    r"\bwhat happened (?:next|was|is)?\s*$",
    r"\bthe problem (?:is|was)?\s*$",
    r"\bthe question (?:is|was)?\s*$",
    r"\band then\s*$",
    r"\bbut then\s*$",
    r"\buntil\s*$",
)


def duration_bounds(content_type: str, preference: str = "auto") -> tuple[int, int]:
    """Return soft target bounds without turning clip length into a hard cutoff."""
    low, high = DURATION_GUIDES.get(content_type, DURATION_GUIDES["other"])
    pref = (preference or "auto").lower().strip()
    if pref == "short":
        short_low = max(8, round(low * 0.65))
        short_high = max(short_low + 8, round(high * 0.72))
        return short_low, min(60, short_high)
    if pref == "longer":
        long_low = max(low, round(low * 1.15))
        long_high = min(120, max(long_low + 18, round(high * 1.45)))
        return long_low, long_high
    # Auto and Balanced use the content-aware guide. Auto still allows natural
    # boundary extension beyond this range when the thought needs it.
    return low, high


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


def _starts_with_any(text: str, phrases: tuple[str, ...]) -> bool:
    lower = _clean(text).lower().lstrip('"“‘')
    return any(lower.startswith(phrase) for phrase in phrases)


def _last_closure_end(text: str) -> int:
    lower = _clean(text).lower()
    positions: list[int] = []
    for cue in NARRATIVE_CLOSURE_CUES:
        pos = lower.rfind(cue)
        if pos >= 0:
            positions.append(pos + len(cue))
    for pattern in NARRATIVE_CLOSURE_PATTERNS:
        positions.extend(match.end() for match in re.finditer(pattern, lower))
    return max(positions) if positions else -1


def _has_closure(text: str) -> bool:
    return _last_closure_end(text) >= 0


def _open_loop_near_end(text: str) -> bool:
    lower = _clean(text).lower().rstrip(' .!?…"”’')
    tail = lower[-180:]
    if any(re.search(pattern, tail) for pattern in OPEN_LOOP_PATTERNS):
        return True
    # A late pivot normally needs the consequence/payoff that follows it.
    last_third = lower[max(0, int(len(lower) * .66)):]
    return any(cue in last_third for cue in ("but ", "however", "until ", "the problem was", "turns out")) and not _has_closure(last_third)


def _opening_context_penalty(segments: list[TranscriptSegment], start_index: int, scene_first: int) -> tuple[int, list[str]]:
    if start_index <= scene_first:
        return 0, []
    opening = _clean(segments[start_index].text).lower().lstrip('"“‘')
    previous = segments[start_index - 1]
    gap = max(0.0, segments[start_index].start - previous.end)
    penalty = 0
    reasons: list[str] = []
    first_words = _words(opening[:90])
    first = first_words[0] if first_words else ""
    if _starts_with_any(opening, RESPONSE_STARTS) and gap < 2.0:
        penalty += 28
        reasons.append("Starts like a reply without the setup")
    elif first in {"he", "she", "they", "it", "this", "that", "these", "those", "him", "her", "them"} and gap < 1.5:
        penalty += 18
        reasons.append("Opening depends on earlier context")
    elif not _starts_clean(segments[start_index].text) and gap < 1.2:
        penalty += 15
        reasons.append("Opening is grammatically dependent")
    if previous.text.rstrip().endswith("?") and gap < 2.0:
        penalty += 18
        reasons.append("Answer needs the preceding question")
    return min(45, penalty), reasons


def _semantic_overlap(left: str, right: str) -> float:
    left_tokens = _topic_tokens(left)
    right_tokens = _topic_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))


def _short_reaction(text: str) -> bool:
    clean = _clean(text).lower().lstrip('"“‘')
    words = _words(clean)
    if not words or len(words) > 14:
        return False
    return _starts_with_any(clean, REACTION_STARTS) or clean in {"yes", "no", "yeah", "wow", "whoa"}


def _boundary_confidence(segments: list[TranscriptSegment], start_index: int, end_index: int, scene: Scene,
                         narrative: int, continuation: int) -> int:
    start_seg = segments[start_index]
    end_seg = segments[end_index]
    previous = segments[start_index - 1] if start_index > scene.first else None
    following = segments[end_index + 1] if end_index < scene.last else None
    gap_before = max(0.0, start_seg.start - previous.end) if previous else 10.0
    gap_after = max(0.0, following.start - end_seg.end) if following else 10.0
    score = 48 + narrative * 0.42
    if start_index == scene.first or gap_before >= 0.65 or _starts_clean(start_seg.text):
        score += 8
    if end_index == scene.last or gap_after >= 0.75 or _ending_quality(end_seg, following) >= 2:
        score += 10
    if continuation == 1:
        score -= 12
    elif continuation >= 2:
        score -= 30
    opening_penalty, _ = _opening_context_penalty(segments, start_index, scene.first)
    score -= opening_penalty * 0.35
    return max(1, min(99, round(score)))


def _narrative_assessment(segments: list[TranscriptSegment], start_index: int, end_index: int, scene: Scene) -> tuple[int, int, list[str], list[str]]:
    """Return (completeness, continuation_level, strengths, warnings).

    continuation_level: 0 = natural stop, 1 = probably continues, 2 = strongly incomplete.
    This is deliberately heuristic and local: it protects story boundaries without
    forcing every clip to become longer.
    """
    start_seg = segments[start_index]
    end_seg = segments[end_index]
    following = segments[end_index + 1] if end_index < scene.last else None
    text = _clean(" ".join(s.text for s in segments[start_index:end_index + 1]))
    lower = text.lower()
    strengths: list[str] = []
    warnings: list[str] = []
    score = 88

    opening_penalty, opening_reasons = _opening_context_penalty(segments, start_index, scene.first)
    score -= opening_penalty
    warnings.extend(opening_reasons)
    if opening_penalty == 0:
        strengths.append("Enough setup to understand the moment")

    continuation = 0
    gap_after = max(0.0, following.start - end_seg.end) if following else 10.0
    next_lower = _clean(following.text).lower().lstrip('"“‘') if following else ""
    current_tail = " ".join(s.text for s in segments[max(start_index, end_index - 1):end_index + 1])
    semantic_follow = _semantic_overlap(current_tail, following.text) if following else 0.0

    if _unfinished(end_seg.text):
        continuation = 2
        score -= 38
        warnings.append("Sentence or thought is unfinished")
    elif end_seg.text.rstrip().endswith("?") and following and gap_after < 2.2:
        continuation = 2
        score -= 34
        warnings.append("Question is answered immediately after the cut")
    elif _open_loop_near_end(text) and following and gap_after < 2.2:
        continuation = 2
        score -= 30
        warnings.append("Setup or story turn has not paid off yet")
    elif following and gap_after < 1.5 and _starts_with_any(next_lower, STRONG_CONTINUATION_STARTS):
        # If the very next line carries the answer/consequence, prefer including it.
        continuation = 2 if not _has_closure(text[-220:]) else 1
        score -= 26 if continuation == 2 else 12
        warnings.append("The next line contains the immediate payoff")
    elif following and gap_after < 1.15 and _short_reaction(following.text):
        # A short reaction often *is* the payoff in anime/film/comedy. Do not cut
        # immediately before it unless the current candidate already closes strongly.
        continuation = 1 if _has_closure(text[-220:]) else 2
        score -= 11 if continuation == 1 else 24
        warnings.append("Immediate reaction belongs with this moment")
    elif following and gap_after < .9 and semantic_follow >= .45 and not _has_closure(text[-180:]):
        continuation = 2
        score -= 20
        warnings.append("The same idea continues immediately after the cut")
    elif following and gap_after < .55 and not _starts_clean(following.text):
        continuation = 1
        score -= 9
        warnings.append("Dialogue appears to continue immediately")

    # If a clear payoff already happened well before the end and the tail adds no
    # new turn, lightly penalize the overhang. This keeps complete 15–25 s moments
    # short instead of stretching them just because more dialogue exists.
    last_closure = _last_closure_end(text)
    if last_closure >= 0:
        trailing_fraction = (len(lower) - last_closure) / max(1, len(lower))
        trailing_words = len(_words(lower[last_closure:]))
        if trailing_fraction <= .22 or trailing_words <= 4:
            score += 8
            strengths.append("Ends close to the payoff")
        elif (trailing_fraction > .30 or trailing_words >= 7) and not _open_loop_near_end(text):
            score -= 13
            warnings.append("Extra dialogue continues after the main payoff")
    elif continuation == 0 and (_ending_quality(end_seg, following) >= 2 or gap_after >= .8):
        score += 4
        strengths.append("Natural stopping point")

    # Questions earlier in the candidate are fine only when some answer/conclusion
    # follows within the same candidate.
    question_pos = lower.rfind("?")
    if question_pos >= int(len(lower) * .45):
        answer_tail = lower[question_pos + 1:]
        if len(_words(answer_tail)) < 7 and following and gap_after < 2.0:
            continuation = max(continuation, 2)
            score -= 24
            warnings.append("Late question needs its answer")

    # Short reaction/punchline clips can be genuinely complete; don't punish them
    # merely for being short when they have a clean payoff and pause.
    if continuation == 0 and _has_closure(text) and gap_after >= .35:
        score += 4

    # Reward windows that include a compact setup directly before a reply/answer.
    # This helps the earlier, self-contained version beat a flashy but contextless reply.
    if start_index < end_index:
        second = _clean(segments[start_index + 1].text).lower().lstrip('"“‘')
        first_gap = max(0.0, segments[start_index + 1].start - segments[start_index].end)
        if first_gap < 1.5 and (_starts_with_any(second, RESPONSE_STARTS) or segments[start_index].text.rstrip().endswith("?")):
            score += 6
            strengths.append("Includes the setup needed for the response")

    return max(1, min(99, round(score))), continuation, list(dict.fromkeys(strengths)), list(dict.fromkeys(warnings))


def _candidate_duration_cap(content_type: str, preference: str, high: int) -> float:
    pref = (preference or "auto").lower().strip()
    if pref == "short":
        return min(90.0, high + 18.0)
    extra = 45.0 if content_type in {"anime", "film-tv", "documentary", "podcast"} else 35.0
    if pref == "longer":
        extra += 20.0
    return min(145.0, high + extra)


def _short_candidate_is_complete_enough(
    *,
    content_type: str,
    duration: float,
    low: int,
    narrative: int,
    payoff: bool,
    ending_quality: int,
    continuation_level: int,
    text: str,
) -> bool:
    """Allow genuinely short moments without letting fragmentary clips dominate.

    Meme/comedy can naturally resolve in only a few seconds. Story-heavy media is
    held to a higher bar when a candidate falls below its normal soft duration.
    This is an admission gate, not a forced minimum length.
    """
    if duration >= low:
        return True
    if content_type == "meme-comedy":
        return narrative >= 80 and ending_quality >= 1 and continuation_level == 0
    word_count = len(_words(text))
    return (
        narrative >= 92
        and payoff
        and ending_quality >= 2
        and continuation_level == 0
        and word_count >= 12
    )


def _candidate_text_similarity(left: str, right: str) -> float:
    """Topic overlap for Best-3 diversity, using the full candidate text."""
    a = _topic_tokens(left)
    b = _topic_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, min(len(a), len(b)))


def _selection_quality(clip: ClipCandidate) -> int:
    narrative = int((clip.context or {}).get("narrative_completeness") or 0)
    boundary = int((clip.context or {}).get("boundary_confidence") or 0)
    warnings = len((clip.context or {}).get("quality_warnings") or [])
    return max(1, min(99, round(clip.score * .62 + narrative * .24 + boundary * .14 - warnings * 2.5)))


def rank_clip_candidates_m2(segments: list[TranscriptSegment], max_clips: int,
                            context: ContentContext, *, shot_boundaries: list[float] | tuple[float, ...] = (),
                            duration_preference: str = "auto") -> list[ClipCandidate]:
    if not segments or max_clips < 1:
        return []
    scenes = segment_scenes(segments, context, shot_boundaries)
    shot_times = sorted(shot_boundaries)
    low, high = duration_bounds(context.resolved_type, duration_preference)
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
                if duration > _candidate_duration_cap(context.resolved_type, duration_preference, high):
                    break
                text_parts.append(end_seg.text)
                if duration < max(5.0, low - 5):
                    continue
                following = segments[end_index + 1] if end_index < scene.last else None
                ending_quality = _ending_quality(end_seg, following)
                narrative, continuation_level, narrative_strengths, narrative_warnings = _narrative_assessment(
                    segments, start_index, end_index, scene
                )
                # Strongly incomplete candidates are not emitted yet. The loop keeps
                # extending until the answer/payoff or a real scene boundary arrives.
                if ending_quality < 1 or continuation_level >= 2:
                    continue
                text = _clean(" ".join(text_parts))
                if len(_words(text)) < 9 and duration > 15:
                    continue
                gap_before = start_seg.start - preceding.end if preceding else 10.0
                gap_after = following.start - end_seg.end if following else 10.0
                old_score, reasons, breakdown, note = _candidate_score(
                    text, duration, start_seg.text, end_seg.text, gap_before, gap_after)
                complete_start = _starts_clean(start_seg.text) or start_index == scene.first
                payoff = any(phrase in text.lower() for phrase in PAYOFF_PHRASES) or _has_closure(text)
                if not _short_candidate_is_complete_enough(
                    content_type=context.resolved_type,
                    duration=duration,
                    low=low,
                    narrative=narrative,
                    payoff=payoff,
                    ending_quality=ending_quality,
                    continuation_level=continuation_level,
                    text=text,
                ):
                    continue
                turn = any(phrase in text.lower() for phrase in PIVOT_PHRASES)
                story = min(99, round(0.72 * narrative + 0.28 * (
                    40 + (18 if complete_start else 0) + 20 * ending_quality // 2
                    + (12 if payoff else 0) + (8 if turn else 0)
                )))
                hook = any(phrase in start_seg.text.lower()[:110] for phrase in HOOK_PHRASES)
                # The old length reward must not force every result into 24–48 s.
                old_length_bias = 15 if 24 <= duration <= 48 else 8 if 18 <= duration <= 60 else -min(18, abs(duration - 36) * .65)
                score = 0.38 * (old_score - old_length_bias * .62) + 0.62 * (
                    breakdown["Hook"] * .17 + breakdown["Standalone"] * .15
                    + breakdown["Payoff"] * .18 + breakdown["Clarity"] * .10
                    + story * .16 + narrative * .24)
                if duration < low:
                    score -= min(10, (low - duration) * .8)
                elif duration > high:
                    score -= min(9, (duration - high) * .45)
                if not complete_start:
                    score -= 10
                if ending_quality == 1:
                    score -= 8
                if continuation_level == 1:
                    score -= 10
                boundary_confidence = _boundary_confidence(
                    segments, start_index, end_index, scene, narrative, continuation_level
                )
                # Prefer the shortest *complete* version of the same moment. This is a
                # small efficiency reward, never a hard short-length target.
                if narrative >= 86 and continuation_level == 0 and duration > low:
                    efficient_overhang = max(0.0, duration - max(low, 18.0))
                    score -= min(5.0, efficient_overhang * 0.05)
                score += (boundary_confidence - 70) * 0.06
                if narrative >= 88:
                    reasons = ["Narratively complete moment", *reasons]
                reasons = [*narrative_strengths, *reasons]
                if payoff:
                    reasons = ["Complete payoff or takeaway", *reasons]
                if hook:
                    reasons = ["Strong opening hook", *reasons]
                warnings = list(narrative_warnings)
                if "Extra dialogue continues after the main payoff" in narrative_warnings:
                    score -= 14
                if ending_quality == 1:
                    warnings.append("Ending boundary is uncertain")
                if not complete_start:
                    warnings.append("Opening may need more context")
                if not payoff and not turn and narrative < 78:
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
                    score_breakdown={**breakdown, "Story": story, "Narrative": narrative}, editor_note=note,
                    context={"moment_type": _moment_type(text), "scene_id": scene_id,
                             "scene_start": round(scene_start, 3), "scene_end": round(scene_end, 3),
                             "quality_warnings": warnings, "shot_changes": cuts if shot_times else None,
                             "duration_preference": (duration_preference or "auto"),
                             "narrative_completeness": narrative,
                             "narrative_continuation": continuation_level,
                             "boundary_confidence": boundary_confidence,
                             "transcript_confidence": round(confidence, 3) if confidence is not None else None},
                )
                clip.context["selection_quality"] = _selection_quality(clip)
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
    # Score leads. When quality is effectively tied, choose the tighter complete
    # edit and prefer candidates with fewer repair warnings.
    candidates.sort(
        key=lambda item: (
            item[0].context.get("selection_quality", item[0].score),
            item[0].score,
            item[0].context.get("narrative_completeness", 0),
            item[0].context.get("boundary_confidence", 0),
            -len(item[0].context.get("quality_warnings") or []),
            -(item[0].end - item[0].start),
        ),
        reverse=True,
    )

    selected: list[tuple[ClipCandidate, int, str]] = []
    best_quality = int(candidates[0][0].context.get("selection_quality", candidates[0][0].score))
    # For the Best 3, use different scenes/moment types when the alternatives are
    # genuinely close in quality. This prevents three near-copies of one conversation.
    close_candidates = [
        item for item in candidates
        if int(item[0].context.get("selection_quality", item[0].score)) >= best_quality - 14
    ]
    for clip, scene_id, text in close_candidates:
        if len(selected) >= min(3, max_clips):
            break
        moment = (clip.context or {}).get("moment_type") or "unknown"
        chosen_scenes = {item[1] for item in selected}
        chosen_moments = {(item[0].context or {}).get("moment_type") or "unknown" for item in selected}
        remaining_scenes = {item[1] for item in close_candidates} - chosen_scenes
        remaining_moments = {((item[0].context or {}).get("moment_type") or "unknown") for item in close_candidates} - chosen_moments
        if scene_id in chosen_scenes and remaining_scenes:
            continue
        if moment != "unknown" and moment in chosen_moments and remaining_moments - {"unknown"}:
            continue
        if any(
            _too_similar(clip, existing[0])
            or _candidate_text_similarity(text, existing[2]) >= .68
            for existing in selected
        ):
            continue
        selected.append((clip, scene_id, text))

    # Fill any remaining slots from the global quality order. Very weak narrative
    # candidates are skipped while stronger alternatives still exist.
    for clip, scene_id, text in candidates:
        if len(selected) >= max_clips:
            break
        narrative = int((clip.context or {}).get("narrative_completeness") or 0)
        if narrative < 58 and any(
            int((other[0].context or {}).get("narrative_completeness") or 0) >= 72
            for other in candidates
        ):
            continue
        if any(
            _too_similar(clip, item[0])
            or _candidate_text_similarity(text, item[2]) >= .74
            or (scene_id == item[1] and abs(clip.start - item[0].start) < 15)
            for item in selected
        ):
            continue
        selected.append((clip, scene_id, text))

    for clip, _, text in selected:
        generated = generate_clip_copy_local(text, "auto")
        clip.title, clip.social_caption = generated.title, generated.social_caption
    return [clip for clip, _, _ in selected]
