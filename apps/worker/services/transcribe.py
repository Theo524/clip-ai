from __future__ import annotations

from functools import lru_cache
import inspect
import re
from statistics import mean

from models import TranscriptSegment, TranscriptWord


@lru_cache(maxsize=1)
def _load_local_model(model_name: str, device: str, compute_type: str, cpu_threads: int = 4):
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
        cpu_threads=cpu_threads if device == "cpu" else 0,
        num_workers=1,
    )




def clear_local_model_cache() -> None:
    """Release the cached CTranslate2 Whisper model before a lower-memory retry.

    The cache intentionally holds only one model, but on Windows a failed MKL/CTranslate2
    allocation can leave the current model as the largest live object. Clearing the cache
    before retrying with a smaller model gives the allocator the best chance to recover.
    """
    _load_local_model.cache_clear()

def _normalise_word_text(value: str) -> str:
    # faster-whisper commonly returns a leading space on each word. Keeping punctuation
    # but removing transport whitespace makes phrase assembly predictable.
    return (value or "").strip()


def _model_transcribe(
    audio_path: str,
    *,
    model_name: str,
    device: str,
    compute_type: str,
    cpu_threads: int,
    vad_filter: bool,
    beam_size: int,
    language: str | None,
    task: str,
    initial_prompt: str | None,
    hotwords: str | None,
    condition_on_previous_text: bool,
):
    model = _load_local_model(model_name, device, compute_type, cpu_threads)
    kwargs = dict(
        beam_size=max(1, int(beam_size)),
        vad_filter=vad_filter,
        condition_on_previous_text=condition_on_previous_text,
        word_timestamps=True,
        task=task,
    )
    if language:
        kwargs["language"] = language
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt[:220]
    # faster-whisper 1.2+ supports hotwords, but Clip AI may be running against an
    # older compatible build on an existing Windows install. Add them only when the
    # loaded model exposes the parameter so M5 improves proper names without turning
    # a library mismatch into a failed analysis.
    if hotwords:
        try:
            if "hotwords" in inspect.signature(model.transcribe).parameters:
                kwargs["hotwords"] = hotwords[:220]
        except (TypeError, ValueError):
            pass
    return model.transcribe(audio_path, **kwargs)


def transcribe_local_with_timestamps(
    audio_path: str,
    model_name: str = "tiny.en",
    device: str = "cpu",
    compute_type: str = "int8",
    offset_seconds: float = 0.0,
    vad_filter: bool = True,
    cpu_threads: int = 4,
    *,
    language: str | None = None,
    task: str = "transcribe",
    initial_prompt: str | None = None,
    hotwords: str | None = None,
    beam_size: int = 1,
    condition_on_previous_text: bool = True,
) -> list[TranscriptSegment]:
    """Transcribe locally with segment + word-level timestamps.

    Caption words come directly from Whisper rather than being rewritten by the copy
    generator. Clip AI's local speech pipeline is intentionally English-only.
    """
    raw_segments, _info = _model_transcribe(
        audio_path,
        model_name=model_name,
        device=device,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
        vad_filter=vad_filter,
        beam_size=beam_size,
        language=language,
        task=task,
        initial_prompt=initial_prompt,
        hotwords=hotwords,
        condition_on_previous_text=condition_on_previous_text,
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


def transcript_quality(segments: list[TranscriptSegment]) -> dict[str, float | int | bool]:
    """Estimate whether a chunk deserves a slower accuracy rescue pass.

    A chunk can look fine on average while one important sentence is wrong. v23.4
    therefore tracks both whole-chunk confidence and the weakest real sentence.
    """
    probabilities: list[float] = []
    tokens: list[str] = []
    segment_count = 0
    weak_segments = 0
    segment_averages: list[float] = []
    for segment in segments:
        if not (segment.text or "").strip():
            continue
        segment_count += 1
        local_probs: list[float] = []
        local_tokens = 0
        for word in segment.words:
            clean = re.sub(r"[^\w']+", "", word.text.lower(), flags=re.UNICODE)
            if clean:
                tokens.append(clean)
                local_tokens += 1
            if word.probability is not None:
                value = float(word.probability)
                probabilities.append(value)
                local_probs.append(value)
        if local_probs and local_tokens >= 3:
            seg_avg = mean(local_probs)
            segment_averages.append(seg_avg)
            if seg_avg < 0.56 or (sum(1 for value in local_probs if value < 0.38) / len(local_probs)) > 0.28:
                weak_segments += 1

    avg_probability = mean(probabilities) if probabilities else (0.74 if segment_count else 0.0)
    low_ratio = (
        sum(1 for value in probabilities if value < 0.48) / len(probabilities)
        if probabilities else (0.0 if segment_count else 1.0)
    )
    very_low_ratio = (
        sum(1 for value in probabilities if value < 0.25) / len(probabilities)
        if probabilities else (0.0 if segment_count else 1.0)
    )
    weakest_segment = min(segment_averages) if segment_averages else avg_probability

    repeated = 0
    for size in (2, 3, 4):
        if len(tokens) < size * 2:
            continue
        for index in range(size, len(tokens) - size + 1):
            if tokens[index - size:index] == tokens[index:index + size]:
                repeated += 1
    repeat_ratio = repeated / max(1, len(tokens))

    score = avg_probability * 100.0
    score -= low_ratio * 24.0
    score -= very_low_ratio * 26.0
    score -= min(18.0, repeat_ratio * 120.0)
    score -= min(12.0, weak_segments * 2.5)
    if segment_count == 0:
        score = 0.0
    score = max(0.0, min(100.0, score))
    needs_refinement = bool(
        segment_count
        and (
            avg_probability < 0.72
            or low_ratio > 0.18
            or very_low_ratio > 0.07
            or repeat_ratio > 0.035
            or weakest_segment < 0.50
            or weak_segments >= 2
        )
    )
    return {
        "score": round(score, 2),
        "average_word_probability": round(avg_probability, 4),
        "weakest_segment_probability": round(weakest_segment, 4),
        "weak_segment_count": weak_segments,
        "low_confidence_ratio": round(low_ratio, 4),
        "very_low_confidence_ratio": round(very_low_ratio, 4),
        "repeat_ratio": round(repeat_ratio, 4),
        "word_count": len(tokens),
        "segment_count": segment_count,
        "needs_refinement": needs_refinement,
    }

def choose_better_transcript(
    first: list[TranscriptSegment], second: list[TranscriptSegment]
) -> tuple[list[TranscriptSegment], dict[str, float | int | bool], bool]:
    first_quality = transcript_quality(first)
    second_quality = transcript_quality(second)
    first_score = float(first_quality["score"])
    second_score = float(second_quality["score"])
    first_low = float(first_quality["low_confidence_ratio"])
    second_low = float(second_quality["low_confidence_ratio"])
    first_weak = float(first_quality["weakest_segment_probability"])
    second_weak = float(second_quality["weakest_segment_probability"])
    # Accept a rescue pass when it clearly improves either the overall transcript or
    # the weakest sentence. This catches isolated wrong lines hidden by a good average.
    use_second = bool(
        second
        and (
            not first
            or second_score >= first_score + 1.5
            or second_low <= first_low - 0.04
            or (second_weak >= first_weak + 0.10 and second_score >= first_score - 5.0)
        )
    )
    chosen = second if use_second else first
    return chosen, (second_quality if use_second else first_quality), use_second

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
