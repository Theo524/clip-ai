from models import TranscriptSegment, TranscriptWord
from services.context import candidate_context, resolve_content_context
from services.smart_rank import detect_shot_boundaries, rank_clip_candidates_m2, segment_scenes


def seg(start, end, text, confidence=None):
    words = [TranscriptWord(start=start, end=end, text="word", probability=confidence) for _ in range(5)] if confidence is not None else []
    return TranscriptSegment(start=start, end=end, text=text, words=words)


def ctx(segments, kind="anime", structure="compilation"):
    return resolve_content_context(segments, requested_type=kind, requested_structure=structure)


def test_compilation_keeps_different_topics_in_separate_scenes():
    segments = [
        seg(0, 8, "Here's why the forest wolves hunt in packs."),
        seg(8, 17, "The pack surrounds its prey before the chase begins."),
        seg(17, 25, "In the end the wolves catch food for the young."),
        seg(29, 38, "Here's why rockets must leave the atmosphere."),
        seg(38, 47, "They accelerate to escape the pull of gravity."),
        seg(47, 55, "That's why the fuel is spent in stages."),
    ]
    context = ctx(segments)
    scenes = segment_scenes(segments, context)
    assert [(s.first, s.last) for s in scenes] == [(0, 2), (3, 5)]
    clips = rank_clip_candidates_m2(segments, 6, context)
    assert clips
    assert all(not (c.start < 26 and c.end > 29) for c in clips)
    assert any(c.start < 26 for c in clips) and any(c.start >= 29 for c in clips)
    for clip in clips:
        envelope = candidate_context(context, clip.start, clip.end, clip.context["scene_start"], clip.context["scene_end"])
        assert envelope["local_context_start"] >= clip.context["scene_start"]
        assert envelope["local_context_end"] <= clip.context["scene_end"]


def test_abrupt_fragment_extends_to_answer_even_beyond_duration_guide():
    segments = [
        seg(0, 10, "Here's the surprising reason we stopped the project."),
        seg(10, 20, "At first everyone thought it was a simple budget issue."),
        seg(20, 29, "But the real reason was because"),
        seg(29.2, 42, "we found the safety tests had failed."),
        seg(42.2, 53, "That's why we paused everything and fixed the design."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "meme-comedy", "single-story"))
    assert clips
    assert all(not (28.9 <= clip.end <= 30) for clip in clips)
    assert any(clip.end > 42 for clip in clips)


def test_short_funny_moment_is_not_forced_to_twenty_seconds():
    segments = [seg(0, 4, "Why did the robot quit?"), seg(4.1, 10, "It needed to recharge its batteries!")]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "meme-comedy", "single-story"))
    assert clips and clips[0].end - clips[0].start < 12


def test_best_three_use_distinct_scenes_and_expose_quality_metadata():
    segments = []
    topics = ["forest wolves hunting in the dark", "astronauts launching a rocket toward orbit",
              "chefs baking a cake in the kitchen", "football players defending the stadium"]
    for i in range(4):
        offset = i * 43
        segments += [seg(offset, offset + 10, f"Here's the truth about {topics[i]}.", .4 if i == 0 else .9),
                     seg(offset + 10, offset + 21, f"At first this {topics[i]} idea seemed impossible."),
                     seg(offset + 21, offset + 31, f"But then this {topics[i]} answer became obvious."),
                     seg(offset + 31, offset + 40, f"That's why the {topics[i]} plan changed.")]
    context = ctx(segments, "podcast", "compilation")
    clips = rank_clip_candidates_m2(segments, 6, context)
    assert len(clips) >= 4
    assert len({clip.context["scene_id"] for clip in clips[:3]}) == 3
    assert all("moment_type" in clip.context and "quality_warnings" in clip.context for clip in clips)


def test_low_confidence_is_flagged_on_selected_moment():
    segments = [seg(0, 8, "Here's why the plan changed.", .3),
                seg(8, 17, "We learned the safety tests failed.", .3),
                seg(17, 25, "That's why we built it again.", .3)]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "other", "single-story"))
    assert clips and "Low transcript confidence" in clips[0].context["quality_warnings"]


def test_shot_sampling_failure_falls_back_to_transcript(monkeypatch):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr("services.smart_rank.subprocess.run", unavailable)
    assert detect_shot_boundaries("missing.mp4") == []


def test_busy_shots_warn_without_splitting_continuous_dialogue():
    segments = [seg(0, 9, "Here's why this scene mattered."),
                seg(9, 18, "The plan failed, but everyone stayed together."),
                seg(18, 27, "The reason was an unexpected change."),
                seg(27, 36, "That's why they finally got home.")]
    context = ctx(segments, "anime", "single-story")
    shots = list(range(2, 36, 2))
    assert len(segment_scenes(segments, context, shots)) == 1
    clips = rank_clip_candidates_m2(segments, 3, context, shot_boundaries=shots)
    assert any("Frequent shot changes: review framing" in clip.context["quality_warnings"] for clip in clips)
    assert all("Visual" in clip.score_breakdown for clip in clips)
