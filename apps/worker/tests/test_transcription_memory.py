from pathlib import Path

import main
from models import TranscriptSegment


def test_numpy_style_allocation_errors_are_recognized():
    assert main._is_memory_allocation_error(MemoryError("no room"))
    assert main._is_memory_allocation_error(RuntimeError(
        "Unable to allocate 141. MiB for an array with shape (1, 45812, 201) and data type complex128"
    ))
    assert not main._is_memory_allocation_error(RuntimeError("bad codec"))


def test_memory_safe_transcription_splits_only_the_failing_chunk(tmp_path, monkeypatch):
    source = tmp_path / "audio_000.mp3"
    source.write_bytes(b"audio")
    monkeypatch.setattr(main.settings, "transcription_backend", "local")

    calls = []
    def fake_transcribe(path, offset_seconds=0.0, *, vad_filter=True, cpu_threads=None):
        calls.append((Path(path).name, offset_seconds))
        if Path(path) == source:
            raise RuntimeError(
                "Unable to allocate 141. MiB for an array with shape (1, 45812, 201) and data type complex128"
            )
        return [TranscriptSegment(start=offset_seconds, end=offset_seconds + 2, text="Recovered speech.")]

    def fake_extract(_media_path, output_dir, chunk_seconds=120, *, cancel_event=None):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths = []
        for index in range(2):
            item = out / f"audio_{index:03d}.mp3"
            item.write_bytes(b"part")
            paths.append(str(item))
        return paths

    monkeypatch.setattr(main, "_transcribe_chunk", fake_transcribe)
    monkeypatch.setattr(main, "extract_audio_chunks", fake_extract)

    result = main._transcribe_chunk_memory_safe(
        str(source), 300.0, vad_filter=True, cpu_threads=2, split_seconds=120
    )
    assert [round(item.start) for item in result] == [300, 420]
    assert calls[0] == ("audio_000.mp3", 300.0)


def test_memory_safe_transcription_does_not_hide_other_errors(tmp_path, monkeypatch):
    source = tmp_path / "audio.mp3"
    source.write_bytes(b"audio")
    monkeypatch.setattr(main.settings, "transcription_backend", "local")

    def fail(*_args, **_kwargs):
        raise RuntimeError("unsupported codec")

    monkeypatch.setattr(main, "_transcribe_chunk", fail)
    try:
        main._transcribe_chunk_memory_safe(str(source), 0.0, vad_filter=True, cpu_threads=2)
    except RuntimeError as exc:
        assert "unsupported codec" in str(exc)
    else:
        raise AssertionError("Non-memory failures must not be swallowed")


def test_mkl_malloc_allocation_error_is_recognized():
    assert main._is_memory_allocation_error(RuntimeError("mkl_malloc: failed to allocate memory"))


def test_stronger_english_model_falls_back_on_mkl_oom(tmp_path, monkeypatch):
    source = tmp_path / "english_chunk.mp3"
    source.write_bytes(b"audio")
    monkeypatch.setattr(main.settings, "transcription_backend", "local")
    monkeypatch.setattr(main.settings, "local_whisper_refine_model", "base.en")
    monkeypatch.setattr(main.settings, "local_whisper_model", "tiny.en")

    calls = []
    def fake_transcribe(path, offset_seconds=0.0, *, vad_filter=True, cpu_threads=None, options=None):
        model = (options or {}).get("model_name")
        calls.append((model, cpu_threads))
        if model == "base.en":
            raise RuntimeError("mkl_malloc: failed to allocate memory")
        return [TranscriptSegment(start=offset_seconds, end=offset_seconds + 2, text="Recovered English speech.")]

    monkeypatch.setattr(main, "_transcribe_chunk", fake_transcribe)
    import services.transcribe as transcribe_service
    monkeypatch.setattr(transcribe_service, "clear_local_model_cache", lambda: None)

    result = main._transcribe_chunk_memory_safe(
        str(source),
        0.0,
        vad_filter=True,
        cpu_threads=4,
        options={"model_name": "base.en", "task": "transcribe", "language": "en", "beam_size": 2},
    )
    assert result and result[0].text == "Recovered English speech."
    assert calls[0][0] == "base.en"
    assert calls[1][0] == "tiny.en"
    assert calls[1][1] <= 2
