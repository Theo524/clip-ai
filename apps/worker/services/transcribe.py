from functools import lru_cache

from models import TranscriptSegment, TranscriptWord


@lru_cache(maxsize=2)
def _load_local_model(model_name: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Local Whisper is not installed. Run: pip install -r requirements.txt"
        ) from exc

    return WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
    )


def _normalise_word_text(value: str) -> str:
    # faster-whisper commonly returns a leading space on each word. Keeping punctuation
    # but removing the transport whitespace makes phrase assembly predictable.
    return (value or "").strip()


def transcribe_local_with_timestamps(
    audio_path: str,
    model_name: str = "tiny.en",
    device: str = "cpu",
    compute_type: str = "int8",
    offset_seconds: float = 0.0,
) -> list[TranscriptSegment]:
    """Transcribe locally with segment + word-level timestamps.

    Word timing costs a little more CPU than segment-only transcription, but it lets
    rendered captions follow the speech instead of evenly guessing timing across a
    sentence. CPU + int8 remains the safest Windows default for the development PC.
    """
    model = _load_local_model(model_name, device, compute_type)
    raw_segments, _info = model.transcribe(
        audio_path,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=True,
        word_timestamps=True,
    )

    segments: list[TranscriptSegment] = []
    for segment in raw_segments:
        text = (segment.text or "").strip()
        if not text:
            continue

        words: list[TranscriptWord] = []
        for word in getattr(segment, "words", None) or []:
            word_text = _normalise_word_text(getattr(word, "word", ""))
            start = getattr(word, "start", None)
            end = getattr(word, "end", None)
            if not word_text or start is None or end is None:
                continue
            probability = getattr(word, "probability", None)
            words.append(
                TranscriptWord(
                    start=float(start) + offset_seconds,
                    end=float(end) + offset_seconds,
                    text=word_text,
                    probability=float(probability) if probability is not None else None,
                )
            )

        segments.append(
            TranscriptSegment(
                start=float(segment.start) + offset_seconds,
                end=float(segment.end) + offset_seconds,
                text=text,
                words=words,
            )
        )
    return segments


def transcribe_openai_with_timestamps(
    audio_path: str,
    api_key: str,
    model: str = "whisper-1",
    offset_seconds: float = 0.0,
) -> list[TranscriptSegment]:
    """Hosted fallback with segment + word timestamps when the model supports them."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=model,
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment", "word"],
        )

    raw_words = getattr(transcript, "words", None) or []
    global_words: list[TranscriptWord] = []
    for word in raw_words:
        start = getattr(word, "start", None)
        end = getattr(word, "end", None)
        text = getattr(word, "word", None)
        if isinstance(word, dict):
            start = word.get("start", start)
            end = word.get("end", end)
            text = word.get("word", text)
        if start is None or end is None or not text:
            continue
        global_words.append(
            TranscriptWord(
                start=float(start) + offset_seconds,
                end=float(end) + offset_seconds,
                text=_normalise_word_text(str(text)),
            )
        )

    segments: list[TranscriptSegment] = []
    for segment in transcript.segments or []:
        start = getattr(segment, "start", None)
        end = getattr(segment, "end", None)
        text = getattr(segment, "text", None)
        if isinstance(segment, dict):
            start = segment.get("start", start)
            end = segment.get("end", end)
            text = segment.get("text", text)
        if start is None or end is None or not text:
            continue

        absolute_start = float(start) + offset_seconds
        absolute_end = float(end) + offset_seconds
        words = [
            word
            for word in global_words
            if word.end > absolute_start - 0.01 and word.start < absolute_end + 0.01
        ]
        segments.append(
            TranscriptSegment(
                start=absolute_start,
                end=absolute_end,
                text=str(text).strip(),
                words=words,
            )
        )
    return segments
