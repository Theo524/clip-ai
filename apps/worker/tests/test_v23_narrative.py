from models import TranscriptSegment
from services.context import resolve_content_context
from services.smart_rank import RANKING_VERSION, rank_clip_candidates_m2


def seg(start, end, text):
    return TranscriptSegment(start=start, end=end, text=text)


def context(segments, content_type="anime"):
    return resolve_content_context(
        segments,
        requested_type=content_type,
        requested_structure="single-story",
    )


def test_v23_ranking_checkpoint_version_changes():
    assert RANKING_VERSION == "v23-narrative-v1"


def test_question_is_not_cut_before_immediate_answer_and_consequence():
    segments = [
        seg(0, 8, "Why did the captain abandon the ship?"),
        seg(8.2, 17, "Because the engine room was already on fire."),
        seg(17.2, 25, "That decision saved everyone on board."),
        seg(29, 37, "The next morning they returned to the harbor."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, context(segments, "film-tv"))
    assert clips
    assert clips[0].end >= 25
    assert clips[0].context["narrative_completeness"] >= 80
    assert "Narrative" in clips[0].score_breakdown


def test_late_story_turn_extends_to_documentary_payoff_when_needed():
    segments = [
        seg(0, 10, "At first the wolves seemed to be changing only the elk population."),
        seg(10.1, 20, "But then researchers noticed the river banks changing too."),
        seg(20.1, 31, "The reason was that fewer elk stayed in the valleys."),
        seg(31.2, 43, "That allowed young trees to grow back along the water."),
        seg(43.2, 55, "That is why the return of wolves reshaped the entire ecosystem."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, context(segments, "documentary"))
    assert clips
    assert clips[0].end >= 55
    assert clips[0].end - clips[0].start > 45
    assert clips[0].context["narrative_continuation"] == 0


def test_complete_short_punchline_stays_short_instead_of_being_padded():
    segments = [
        seg(0, 4, "Why did the robot quit?"),
        seg(4.1, 10, "It needed to recharge its batteries!"),
        seg(14, 22, "Now for something completely different about space travel."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, context(segments, "meme-comedy"))
    assert clips
    assert clips[0].end - clips[0].start < 12
    assert clips[0].context["narrative_completeness"] >= 80


def test_pronoun_only_opening_loses_to_version_with_needed_setup():
    segments = [
        seg(0, 9, "Mika had only one chance to stop the attack."),
        seg(9.1, 18, "She ran toward the gate before anyone could react."),
        seg(18.1, 27, "But then the enemy changed direction."),
        seg(27.1, 38, "That is why she had to abandon the original plan."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, context(segments, "anime"))
    assert clips
    assert clips[0].start < 1
    assert clips[0].hook.startswith("Mika")


def test_narrative_extension_never_crosses_scene_boundary():
    segments = [
        seg(0, 8, "Why did the hero leave the city?"),
        seg(8.1, 18, "Because the bridge was about to collapse."),
        seg(18.1, 27, "That is why everyone escaped in time."),
        # Clear scene break / local topic change.
        seg(32, 41, "Here's why deep sea whales can dive for so long."),
        seg(41.1, 50, "Their bodies store oxygen very differently."),
    ]
    ctx = resolve_content_context(segments, requested_type="anime", requested_structure="compilation")
    clips = rank_clip_candidates_m2(segments, 4, ctx)
    assert clips
    assert all(not (clip.start < 30 and clip.end > 31) for clip in clips)
