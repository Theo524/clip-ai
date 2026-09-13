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
