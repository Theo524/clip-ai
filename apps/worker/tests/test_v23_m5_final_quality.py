from pathlib import Path

import main
from models import TranscriptSegment, TranscriptWord
from services import transcribe
from services.captions import write_clip_ass
from services.context import resolve_content_context
from services.copywriter import generate_clip_copy_local
from services.smart_rank import rank_clip_candidates_m2


def seg(start: float, end: float, text: str):
    return TranscriptSegment(start=start, end=end, text=text)


def ctx(segments, content_type="film-tv"):
    return resolve_content_context(
        segments,
        requested_type=content_type,
        requested_structure="single-story",
    )


def test_m5_release_is_english_only_and_invalidates_old_speech_cache():
    assert main.APP_VERSION == "23.0.0-beta.9"
    assert main.RELEASE_NAME == "M5 Final Quality Pass"
    assert main.TRANSCRIPTION_VERSION == "v23.5-english-quality"
    assert "english" in main._transcription_strategy().lower()


def test_m5_subject_hint_builds_trusted_hotwords_without_filename_noise():
    value = main._whisper_hotwords("Attack on Titan, Season 3")
    assert value is not None
    assert "Attack on Titan" in value
    assert "Titan" in value
    assert "episode8.mkv" not in value
    assert main._whisper_hotwords(None) is None


def test_m5_passes_hotwords_only_when_local_whisper_supports_them(monkeypatch):
    seen = {}

    class FakeModel:
        def transcribe(
            self, audio_path, *, beam_size, vad_filter, condition_on_previous_text,
            word_timestamps, task, language=None, initial_prompt=None, hotwords=None,
        ):
            seen["hotwords"] = hotwords
            return [], object()

    monkeypatch.setattr(transcribe, "_load_local_model", lambda *args, **kwargs: FakeModel())
    transcribe._model_transcribe(
        "audio.mp3",
        model_name="base.en",
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        vad_filter=True,
        beam_size=3,
        language="en",
        task="transcribe",
        initial_prompt="Attack on Titan.",
        hotwords="Attack on Titan, Attack, Titan",
        condition_on_previous_text=True,
    )
    assert seen["hotwords"] == "Attack on Titan, Attack, Titan"


def test_m5_local_whisper_stays_compatible_when_hotwords_are_unavailable(monkeypatch):
    class OlderFakeModel:
        def transcribe(
            self, audio_path, *, beam_size, vad_filter, condition_on_previous_text,
            word_timestamps, task, language=None, initial_prompt=None,
        ):
            return [], object()

    monkeypatch.setattr(transcribe, "_load_local_model", lambda *args, **kwargs: OlderFakeModel())
    segments, _ = transcribe._model_transcribe(
        "audio.mp3",
        model_name="tiny.en",
        device="cpu",
        compute_type="int8",
        cpu_threads=2,
        vad_filter=True,
        beam_size=1,
        language="en",
        task="transcribe",
        initial_prompt="Attack on Titan.",
        hotwords="Attack on Titan",
        condition_on_previous_text=True,
    )
    assert segments == []


def test_m5_copy_prefers_complete_specific_clause_over_blind_truncation():
    generated = generate_clip_copy_local(
        "I thought the plan would work because everyone agreed to it, but the final test proved the entire design was wrong and we had to rebuild it from scratch.",
        content_type="documentary",
        moment_type="reveal",
    )
    assert "final test" in generated.title.lower()
    assert generated.title.split()[-1].lower() not in {"and", "but", "because", "the", "with", "to"}
    assert not generated.description.lower().endswith((" and.", " we.", " they.", " because."))
    assert "#Shorts" not in generated.hashtags


def test_m5_metadata_restores_trusted_subject_casing_without_inventing_names():
    generated = generate_clip_copy_local(
        "attack on titan changed the way everyone understood the walls. the truth was hidden inside them.",
        subject_hint="Attack on Titan",
        content_type="anime",
        moment_type="reveal",
    )
    combined = f"{generated.title} {generated.description} {' '.join(generated.hashtags)}"
    assert "Attack on Titan" in combined
    assert "attack on titan" not in combined.replace("Attack on Titan", "")
    for invented in ("Eren", "Mikasa", "Levi"):
        assert invented not in combined


def test_m5_cinematic_captions_use_intentional_balanced_line_breaks(tmp_path: Path):
    words = []
    cursor = 0.0
    for token in "This is the reason the whole plan suddenly fell apart".split():
        words.append(TranscriptWord(start=cursor, end=cursor + 0.24, text=token, probability=0.95))
        cursor += 0.29
    segments = [TranscriptSegment(start=0.0, end=cursor, text="This is the reason the whole plan suddenly fell apart", words=words)]
    target = tmp_path / "m5.ass"
    path, timed = write_clip_ass(
        segments,
        0.0,
        cursor + 0.2,
        str(target),
        caption_style="cinematic",
        layout_mode="focus",
        frame_size="compact",
        caption_zone="lower",
        content_type="film-tv",
    )
    text = Path(path).read_text(encoding="utf-8-sig")
    assert timed is True
    assert r"\N" in text
    assert "the\\N" not in text.lower()
    assert "because\\N" not in text.lower()


def test_m5_strong_reaction_is_kept_even_after_a_spoken_closure():
    segments = [
        seg(0, 7, "The lock finally clicked and the vault opened."),
        seg(7.1, 14, "That was the answer the detective needed."),
        seg(14.1, 17, "No way, he actually solved it!"),
        seg(21, 30, "Later they returned to the station for paperwork."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "film-tv"))
    assert clips
    assert clips[0].end >= 17
    assert clips[0].context.get("narrative_continuation") == 0


def test_m5_ranked_clips_record_manual_boundary_repair_cost():
    segments = [
        seg(0, 8, "Why did the crew turn the ship around?"),
        seg(8.1, 17, "Because the radar showed the storm moving directly toward them."),
        seg(17.1, 25, "That was why they reached the harbour safely."),
    ]
    clips = rank_clip_candidates_m2(segments, 2, ctx(segments, "documentary"))
    assert clips
    cost = clips[0].context.get("boundary_repair_cost")
    assert isinstance(cost, int)
    assert 0 <= cost <= 35
