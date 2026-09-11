from functools import lru_cache

from models import TranscriptSegment


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


def transcribe_local_with_timestamps(
    audio_path: str,
    model_name: str = "small.en",
    device: str = "cpu",
    compute_type: str = "int8",
    offset_seconds: float = 0.0,
) -> list[TranscriptSegment]:
    """Transcribe audio locally with faster-whisper.

    The model is downloaded automatically on first use and then cached on disk.
    CPU + int8 is the safest Windows default and does not require CUDA.
    """
    model = _load_local_model(model_name, device, compute_type)
    raw_segments, _info = model.transcribe(
        audio_path,
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=True,
    )

    segments: list[TranscriptSegment] = []
    for segment in raw_segments:
        text = (segment.text or "").strip()
        if text:
            segments.append(
                TranscriptSegment(
                    start=float(segment.start) + offset_seconds,
                    end=float(segment.end) + offset_seconds,
                    text=text,
                )
            )
    return segments


def transcribe_openai_with_timestamps(
    audio_path: str,
    api_key: str,
    model: str = "whisper-1",
    offset_seconds: float = 0.0,
) -> list[TranscriptSegment]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model=model,
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
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
        if start is not None and end is not None and text:
            segments.append(
                TranscriptSegment(
                    start=float(start) + offset_seconds,
                    end=float(end) + offset_seconds,
                    text=str(text).strip(),
                )
            )
    return segments
