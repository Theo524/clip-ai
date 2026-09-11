from models import TranscriptSegment
from services.copywriter import dialogue_for_range, generate_clip_copy_local


def test_dialogue_for_range_uses_only_overlapping_segments():
    segments = [
        TranscriptSegment(start=0, end=4, text="Before the clip."),
        TranscriptSegment(start=4, end=9, text="The biggest mistake I made was hiring too quickly."),
        TranscriptSegment(start=9, end=14, text="That's why I now hire slowly."),
        TranscriptSegment(start=14, end=18, text="After the clip."),
    ]
    text = dialogue_for_range(segments, 4.2, 13.8)
    assert "biggest mistake" in text.lower()
    assert "hire slowly" in text.lower()
    assert "Before" not in text
    assert "After" not in text


def test_auto_copy_turns_dialogue_into_a_short_title_and_caption():
    generated = generate_clip_copy_local(
        "The biggest mistake I made was hiring too quickly. I thought speed mattered more than fit. That's why I now hire slowly and test for values first.",
        "auto",
    )
    assert generated.title
    assert len(generated.title) <= 58
    assert "mistake" in generated.title.lower()
    assert generated.social_caption
    assert "hire" in generated.social_caption.lower()


def test_cinematic_copy_is_restrained():
    generated = generate_clip_copy_local(
        "You knew this would happen. I told you there would be a price. In the end, we both paid it.",
        "cinematic",
    )
    assert len(generated.title.split()) <= 7
    assert len(generated.social_caption) <= 170


def test_social_caption_uses_supporting_dialogue_when_title_repeats_hook():
    generated = generate_clip_copy_local(
        "The biggest mistake I made was hiring too quickly. Three months later, half the team had already left. That's why I now hire slowly and test for values first.",
        "viral",
    )
    assert generated.title
    assert generated.social_caption
    assert "hire slowly" in generated.social_caption.lower() or "team" in generated.social_caption.lower()
    assert generated.social_caption.lower() != generated.title.lower()
