from models import TranscriptSegment, TranscriptWord
import main
from services.copywriter import generate_clip_copy_local
from services.transcribe import choose_better_transcript, transcript_quality


def test_auto_audio_prefers_english_track_when_labelled():
    info = {
        "default_audio_track": 1,
        "audio_tracks": [
            {"track": 1, "language": "jpn", "title": "Japanese", "default": True},
            {"track": 2, "language": "eng", "title": "English Dub", "default": False},
        ],
    }
    assert main._choose_automatic_audio_track(info) == 2
    assert main._audio_track_language(info, 2) == "en"


def test_language_aliases_cover_anime_metadata():
    assert main._normalize_language_code("jpn") == "ja"
    assert main._normalize_language_code("eng") == "en"
    assert main._normalize_language_code("en-US") == "en"



def test_explicit_non_english_track_is_rejected_cleanly():
    info = {"audio_tracks": [{"track": 1, "language": "jpn", "title": "Japanese", "default": True}]}
    try:
        main._validate_english_audio(info, 1)
    except RuntimeError as exc:
        assert "English-only" in str(exc)
        assert "English dub" in str(exc)
    else:
        raise AssertionError("Clearly labelled non-English audio should not be silently mistranscribed")

def test_subject_hint_is_the_only_whisper_prompt_source():
    assert main._whisper_prompt("Attack on Titan", "episode8.mkv") == "Attack on Titan."
    assert main._whisper_prompt(None, "episode8.mkv") is None


def test_transcript_quality_catches_one_weak_sentence():
    good_words = [
        TranscriptWord(start=0.0, end=0.4, text="This", probability=0.95),
        TranscriptWord(start=0.4, end=0.8, text="line", probability=0.94),
        TranscriptWord(start=0.8, end=1.2, text="works", probability=0.93),
    ]
    weak_words = [
        TranscriptWord(start=1.3, end=1.7, text="mangled", probability=0.22),
        TranscriptWord(start=1.7, end=2.1, text="anime", probability=0.29),
        TranscriptWord(start=2.1, end=2.5, text="name", probability=0.25),
    ]
    quality = transcript_quality([
        TranscriptSegment(start=0, end=1.2, text="This line works.", words=good_words),
        TranscriptSegment(start=1.3, end=2.5, text="Mangled anime name.", words=weak_words),
    ])
    assert quality["needs_refinement"] is True
    assert quality["weak_segment_count"] >= 1


def test_accuracy_rescue_can_win_on_weak_sentence_even_when_average_is_close():
    first = [TranscriptSegment(start=0, end=1, text="Wrong name here", words=[
        TranscriptWord(start=0, end=.3, text="Wrong", probability=.45),
        TranscriptWord(start=.3, end=.6, text="name", probability=.48),
        TranscriptWord(start=.6, end=1, text="here", probability=.44),
    ])]
    second = [TranscriptSegment(start=0, end=1, text="Correct name here", words=[
        TranscriptWord(start=0, end=.3, text="Correct", probability=.70),
        TranscriptWord(start=.3, end=.6, text="name", probability=.71),
        TranscriptWord(start=.6, end=1, text="here", probability=.69),
    ])]
    chosen, quality, used = choose_better_transcript(first, second)
    assert used is True
    assert chosen[0].text == "Correct name here"
    assert quality["score"] > transcript_quality(first)["score"]


def test_social_tags_are_specific_and_not_padded_with_shorts_filler():
    generated = generate_clip_copy_local(
        "The walls were hiding the truth from everyone. The walls changed what they believed.",
        subject_hint="Attack on Titan",
        content_type="anime",
        moment_type="reveal",
    )
    assert "#AttackOnTitan" in generated.hashtags
    assert "#Anime" in generated.hashtags
    assert "#Reveal" in generated.hashtags
    assert "#Shorts" not in generated.hashtags
    assert "#AnimeClips" not in generated.hashtags
    assert len(generated.hashtags) <= 5


def test_anime_auto_copy_stays_restrained():
    generated = generate_clip_copy_local(
        "They told us the walls were built to protect humanity. But the truth is the walls were hiding something from everyone.",
        subject_hint="Attack on Titan",
        content_type="anime",
        moment_type="reveal",
    )
    assert len(generated.title.split()) <= 11
    assert len(generated.description.split()) <= 24
