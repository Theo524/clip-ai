from models import TranscriptSegment
from services.local_rank import rank_clip_candidates_local


def seg(start: float, end: float, text: str) -> TranscriptSegment:
    return TranscriptSegment(start=start, end=end, text=text)


def test_prefers_clean_hook_and_payoff_over_context_lead_in():
    segments = [
        seg(0, 7, "And, um, before that there was some other stuff going on."),
        seg(7, 15, "The biggest mistake I made was hiring too quickly."),
        seg(15, 24, "I thought speed mattered more than finding the right people."),
        seg(24, 34, "But three months later, half the team had already left."),
        seg(34, 44, "That's why I now hire slowly and test for values first."),
        seg(44, 53, "And then, like, there were a few other things as well."),
    ]

    clips = rank_clip_candidates_local(segments, max_clips=3)

    assert clips
    assert 6.5 <= clips[0].start <= 7.1
    assert 43.8 <= clips[0].end <= 44.3
    assert clips[0].score >= 70
    assert any("hook" in reason.lower() for reason in clips[0].reasons)
    assert any("payoff" in reason.lower() or "takeaway" in reason.lower() for reason in clips[0].reasons)


def test_avoids_heavily_overlapping_duplicate_candidates():
    segments = [
        seg(0, 8, "Here's why most people give up too early."),
        seg(8, 17, "They expect progress to be obvious in the first few weeks."),
        seg(17, 27, "But the results usually arrive after the boring part."),
        seg(27, 38, "That's why consistency matters more than motivation."),
        seg(50, 58, "The secret to pricing is understanding the customer's risk."),
        seg(58, 68, "If the risk feels high, even a cheap product can feel expensive."),
        seg(68, 78, "So the best offer removes uncertainty before it lowers price."),
        seg(78, 88, "That's the reason guarantees can change conversion so much."),
    ]

    clips = rank_clip_candidates_local(segments, max_clips=4)

    assert len(clips) >= 2
    assert clips[0].end <= 45 or clips[0].start >= 49
    assert any(c.start >= 49 for c in clips)
    assert any(c.start < 10 for c in clips)


def test_short_transcript_still_returns_one_candidate():
    segments = [
        seg(0, 6, "The answer is surprisingly simple."),
        seg(6, 12, "Start smaller than you think and keep going."),
    ]

    clips = rank_clip_candidates_local(segments, max_clips=3)
    assert len(clips) == 1
    assert clips[0].start == 0
    assert clips[0].end > 12


def test_candidates_expose_editor_score_breakdown():
    segments = [
        seg(0, 8, "Here's why most people quit before the results arrive."),
        seg(8, 18, "They expect progress to feel obvious almost immediately."),
        seg(18, 30, "But the boring middle is where the habit actually forms."),
        seg(30, 42, "That's why consistency matters more than motivation."),
    ]
    clips = rank_clip_candidates_local(segments, max_clips=2)
    assert clips
    assert set(clips[0].score_breakdown) == {"Hook", "Standalone", "Payoff", "Retention", "Clarity"}
    assert all(1 <= value <= 99 for value in clips[0].score_breakdown.values())
    assert clips[0].editor_note
