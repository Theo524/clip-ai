from models import TranscriptSegment
from services.context import resolve_content_context
from services.smart_rank import rank_clip_candidates_m2


def seg(start, end, text):
    return TranscriptSegment(start=start, end=end, text=text)


def ctx(segments, content_type="anime"):
    return resolve_content_context(
        segments,
        requested_type=content_type,
        requested_structure="single-story",
    )


def test_immediate_anime_reaction_is_not_cut_off():
    segments = [
        seg(0, 7, "The door finally opened and the missing captain stepped through."),
        seg(7.1, 14, "Everyone stared because they had believed he was dead."),
        seg(14.1, 18, "No way, you're actually alive!"),
        seg(21, 30, "Later that night the crew returned to their rooms."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "anime"))
    assert clips
    assert clips[0].end >= 18
    assert clips[0].context["narrative_continuation"] == 0


def test_unrelated_next_line_does_not_force_extension():
    segments = [
        seg(0, 7, "Why did the comedian carry a ladder on stage?"),
        seg(7.1, 14, "Because he wanted to take the joke to another level!"),
        seg(17, 26, "Saturn has more than a hundred known moons."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "meme-comedy"))
    assert clips
    assert clips[0].end < 16


def test_compact_setup_beats_contextless_reply():
    segments = [
        seg(0, 6, "What happens if the reactor reaches maximum pressure?"),
        seg(6.1, 13, "Because then the safety system shuts the entire station down."),
        seg(13.1, 20, "That is why the engineers evacuate before the alarm ends."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "documentary"))
    assert clips
    assert clips[0].start < 1
    assert clips[0].hook.startswith("What happens")


def test_same_thought_continuation_is_kept_until_completion():
    segments = [
        seg(0, 9, "The whales survive these dives because their muscles hold huge stores of oxygen."),
        seg(9.1, 18, "Their blood also carries far more oxygen than ours can."),
        seg(18.1, 27, "Together those adaptations let them stay underwater for over an hour."),
        seg(31, 40, "The next species lives much closer to the surface."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "documentary"))
    assert clips
    assert clips[0].end >= 27


def test_boundary_confidence_is_recorded_for_ranked_clips():
    segments = [
        seg(0, 8, "Why did the hero stay behind?"),
        seg(8.1, 16, "Because someone had to hold the gate open."),
        seg(16.1, 24, "That is why the others managed to escape."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "film-tv"))
    assert clips
    confidence = clips[0].context.get("boundary_confidence")
    assert isinstance(confidence, int)
    assert 1 <= confidence <= 99


def test_complete_candidate_does_not_keep_irrelevant_post_payoff_dialogue():
    segments = [
        seg(0, 7, "The thief thought the vault was empty."),
        seg(7.1, 14, "But the final box contained the missing diamond."),
        seg(14.1, 21, "That was the proof the detective needed."),
        seg(21.2, 29, "Afterward they discussed where to eat dinner."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "film-tv"))
    assert clips
    assert clips[0].end <= 22
