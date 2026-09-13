from models import TranscriptSegment
from services.context import candidate_context_payload, clean_subject_hint, detect_content_structure


def seg(start, end, text):
    return TranscriptSegment(start=start, end=end, text=text)


def test_manual_compilation_choice_wins_over_auto_detection():
    detection = detect_content_structure(
        [seg(0, 10, "one continuous scene")],
        duration=60,
        requested_structure="compilation",
        content_type="anime",
    )
    assert detection.detected == "compilation"
    assert detection.confidence == 1.0


def test_podcast_auto_structure_prefers_conversation():
    detection = detect_content_structure(
        [seg(0, 5, "welcome"), seg(5, 12, "today we talk")],
        duration=1800,
        requested_structure="auto",
        content_type="podcast",
    )
    assert detection.detected == "conversation"


def test_short_sources_stay_single_story_conservatively():
    detection = detect_content_structure(
        [seg(0, 20, "a scene"), seg(20, 50, "continues here")],
        duration=90,
        requested_structure="auto",
        content_type="anime",
    )
    assert detection.detected == "single-story"


def test_candidate_context_is_local_and_preserves_hint():
    detection = detect_content_structure(
        [seg(0, 20, "part one")], duration=300, requested_structure="compilation", content_type="anime"
    )
    payload = candidate_context_payload(
        start=100,
        end=125,
        duration=300,
        content_type="anime",
        requested_structure="auto",
        detection=detection,
        subject_hint="  Attack   on Titan  ",
    )
    assert payload["local_context_start"] == 82.0
    assert payload["local_context_end"] == 143.0
    assert payload["subject_hint"] == "Attack on Titan"
    assert clean_subject_hint("  A   B  ") == "A B"


def test_auto_structure_can_detect_compilation_from_topic_resets_and_gap():
    items = [
        seg(0, 20, "dragon kingdom sword battle castle warrior"),
        seg(70, 88, "dragon castle knight warrior battle"),
        seg(190, 210, "recipe kitchen garlic pasta tomato cheese"),
        seg(285, 305, "recipe oven flour sugar butter cake"),
        seg(400, 420, "football striker penalty goalkeeper stadium league"),
        seg(500, 520, "football manager referee stadium goal match"),
    ]
    detection = detect_content_structure(
        items, duration=560, requested_structure="auto", content_type="other"
    )
    assert detection.detected == "compilation"
