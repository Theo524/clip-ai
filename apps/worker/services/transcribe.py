from openai import OpenAI
from models import TranscriptSegment


def transcribe_with_timestamps(audio_path: str, api_key: str) -> list[TranscriptSegment]:
    client = OpenAI(api_key=api_key)

    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    segments = []
    for segment in transcript.segments or []:
        # SDK objects currently expose attributes; tolerate dict-like objects too.
        start = getattr(segment, "start", None)
        end = getattr(segment, "end", None)
        text = getattr(segment, "text", None)
        if isinstance(segment, dict):
            start = segment.get("start", start)
            end = segment.get("end", end)
            text = segment.get("text", text)
        if start is not None and end is not None and text:
            segments.append(TranscriptSegment(start=float(start), end=float(end), text=str(text).strip()))

    return segments
