from models import TranscriptSegment
from services.context import candidate_context, normalize_subject_hint, resolve_content_context


def seg(start, end, text):
    return TranscriptSegment(start=start, end=end, text=text)


def test_user_selected_context_wins_over_auto_detection():
    segments = [seg(0, 5, "Welcome back to the podcast. Today our guest explains the story.")]
    context = resolve_content_context(
        segments,
        requested_type="anime",
        requested_structure="single-story",
        subject_hint="  Attack   on Titan  ",
        project_title="Episode clip",
    )
    assert context.resolved_type == "anime"
    assert context.resolved_structure == "single-story"
    assert context.subject_hint == "Attack on Titan"
    assert context.confidence == 1.0


def test_auto_podcast_context_can_resolve_conversation():
    segments = [
        seg(0, 8, "Welcome back to the podcast. Our guest is here for this episode."),
        seg(8.2, 16, "What did you think when you first saw it?"),
        seg(16.1, 26, "I thought it would never work, but then we changed the plan."),
    ]
    context = resolve_content_context(segments, project_title="My podcast episode")
    assert context.resolved_type == "podcast"
    assert context.resolved_structure == "conversation"


def test_auto_structure_detects_clear_compilation_breaks():
    segments = []
    t = 0.0
    topics = [
        "wolves forest habitat hunting pack alpha territory",
        "spaceship planet astronaut rocket orbit galaxy",
        "cake sugar oven recipe chocolate kitchen",
        "football striker stadium match goalkeeper league",
        "computer graphics processor memory benchmark laptop",
        "ocean shark coral reef diving whale current",
    ]
    for topic in topics:
        for _ in range(8):
            segments.append(seg(t, t + 3.0, topic))
            t += 3.05
        t += 4.5
    context = resolve_content_context(segments, requested_type="other", requested_structure="auto")
    assert context.resolved_structure == "compilation"


def test_candidate_context_uses_tighter_local_envelope_for_compilation():
    segments = [seg(0, 10, "one"), seg(20, 30, "two")]
    context = resolve_content_context(segments, requested_type="anime", requested_structure="compilation", subject_hint="Show")
    data = candidate_context(context, 100, 130)
    assert data["content_type"] == "anime"
    assert data["content_structure"] == "compilation"
    assert data["local_context_start"] == 82.0
    assert data["local_context_end"] == 154.0


def test_subject_hint_is_small_and_normalized():
    value = normalize_subject_hint("  Planet    Earth III  ")
    assert value == "Planet Earth III"
