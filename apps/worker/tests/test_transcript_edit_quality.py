from models import TranscriptSegment, TranscriptWord
from services.transcript_edit import corrected_segment_with_preserved_timing


def test_one_word_correction_keeps_exact_word_times():
    original = [TranscriptSegment(start=1, end=4, text="we saw Erin today", words=[
        TranscriptWord(start=1.0, end=1.3, text="we", probability=.9),
        TranscriptWord(start=1.4, end=1.8, text="saw", probability=.9),
        TranscriptWord(start=2.4, end=2.9, text="Erin", probability=.5),
        TranscriptWord(start=3.2, end=3.8, text="today", probability=.9),
    ])]
    edited = corrected_segment_with_preserved_timing(original, 1, 4, "we saw Eren today")
    assert edited is not None
    assert [round(w.start, 2) for w in edited.words] == [1.0, 1.4, 2.4, 3.2]
    assert edited.words[2].text == "Eren"


def test_changed_word_count_still_preserves_real_pause_shape():
    original = [TranscriptSegment(start=0, end=5, text="wait now", words=[
        TranscriptWord(start=.2, end=.8, text="wait", probability=.9),
        TranscriptWord(start=3.8, end=4.5, text="now", probability=.9),
    ])]
    edited = corrected_segment_with_preserved_timing(original, 0, 5, "wait for me now")
    assert edited is not None
    assert edited.words[0].start >= .19
    assert edited.words[-1].end <= 4.51
    assert edited.words[2].start > 1.0
