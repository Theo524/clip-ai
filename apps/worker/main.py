from pathlib import Path
from concurrent.futures import CancelledError
import json
import gc
import importlib.util
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import re
import shutil
import time
import uuid
import zipfile
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse

from models import AnalyzeRequest, AnalyzeResponse, CleanupResponse, ClipCandidate, ClipCopyGenerateRequest, ClipCopyResponse, ClipCopyUpdateRequest, ClipFeedbackRequest, ClipTimingUpdateRequest, CoverRequest, ProjectCleanupRequest, ProjectCleanupResponse, ProjectDetail, ProjectNotesUpdateRequest, ProjectSummary, RenderClipRequest, RenderClipResponse, SystemCheck, SystemPreflightResponse, TaskCreateResponse, TaskStatusResponse, TranscriptEditRequest, TranscriptRangeResponse, TranscriptSegment, YouTubeInfoResponse
from settings import settings
from services.media import cut_clip, extract_audio_chunks, extract_cover_frame, is_memory_allocation_error, normalize_media, probe_media, probe_media_audio, render_adaptive_short, should_normalize_media
from services.captions import write_clip_ass
from services.mock import mock_clips
from services.reframe import ReframePlan, load_reframe_plan, plan_smart_reframe, save_reframe_plan
from services.layouts import auto_profile, burned_subtitles_likely, choose_caption_style, choose_caption_zone, choose_frame_size, choose_layout
from services.projects import cleanup_project_storage, cleanup_stale_work, directory_size, load_project, rendered_media, save_project, source_available
from services.copywriter import dialogue_for_range, generate_clip_copy_local
from services.tasks import tasks
from services.profiles import get_processing_profile, PROFILES
from services.subtitles_export import to_srt, to_vtt
from services.diagnostics import build_diagnostic_zip
from services.transcript_cache import cleanup_transcript_cache, load_cached_transcript, save_cached_transcript, transcript_cache_key
from services.context import candidate_context, normalize_content_structure, normalize_content_type, normalize_subject_hint, resolve_content_context
from services.smart_rank import RANKING_VERSION, detect_shot_boundaries, rank_clip_candidates_m2
from services.transcript_edit import corrected_segment_with_preserved_timing

APP_VERSION = "23.0.0-beta.9"
RELEASE_NAME = "M5 Final Quality Pass"
TRANSCRIPTION_VERSION = "v23.5-english-quality"

app = FastAPI(title="Clip AI Worker", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_.-]+$")

# Clean leftovers from interrupted local runs when the worker starts.
STARTUP_CLEANUP = cleanup_stale_work(Path(settings.work_dir))
tasks.configure(Path(settings.work_dir))


def safe_download_name(value: str | None, fallback: str = "clip-ai-short") -> str:
    """Return a browser-safe, human-readable MP4 download filename."""
    raw = (value or "").strip()
    if raw.lower().endswith(".mp4"):
        raw = raw[:-4]
    clean = re.sub(r"[^A-Za-z0-9 _-]+", "", raw)
    clean = re.sub(r"[ _]+", "-", clean).strip("-_")[:80]
    if not clean:
        clean = re.sub(r"[^A-Za-z0-9_-]+", "-", fallback).strip("-_") or "clip-ai-short"
    return f"{clean}.mp4"


def is_youtube_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def fetch_youtube_info(source_url: str) -> YouTubeInfoResponse:
    if not is_youtube_url(source_url):
        raise HTTPException(status_code=400, detail="Enter a valid YouTube URL.")

    endpoint = "https://www.youtube.com/oembed?" + urlencode({"url": source_url, "format": "json"})
    request = Request(endpoint, headers={"User-Agent": f"ClipAI/{APP_VERSION}"})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Clip AI could not read this YouTube video's public metadata. Check the link and your internet connection.",
        ) from exc

    return YouTubeInfoResponse(
        source_url=source_url,
        title=str(payload.get("title") or "YouTube video"),
        author_name=payload.get("author_name"),
        thumbnail_url=payload.get("thumbnail_url"),
        provider_name=str(payload.get("provider_name") or "YouTube"),
    )


def _job_dir(job_id: str) -> Path:
    if not SAFE_ID.fullmatch(job_id):
        raise HTTPException(status_code=400, detail="Invalid job id.")
    return Path(settings.work_dir) / job_id


def _find_source(job_id: str) -> Path:
    job_dir = _job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="This analysis job no longer exists.")

    normalized = job_dir / "normalized.mp4"
    if normalized.exists() and normalized.is_file() and normalized.stat().st_size > 0:
        return normalized
    sources = sorted(path for path in job_dir.glob("source.*") if path.is_file())
    if not sources:
        raise HTTPException(status_code=404, detail="Original source video was not found for this job.")
    return sources[0]


def _load_transcript(job_id: str) -> list[TranscriptSegment]:
    transcript_path = _job_dir(job_id) / "transcript.json"
    if not transcript_path.exists():
        raise HTTPException(
            status_code=409,
            detail="This job predates caption storage. Re-analyze the video once, then generate the Short.",
        )
    try:
        raw = json.loads(transcript_path.read_text(encoding="utf-8"))
        return [TranscriptSegment.model_validate(item) for item in raw]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stored transcript could not be read: {exc}") from exc


def _normalize_language_code(value: str | None) -> str:
    raw = (value or "").strip().lower().replace("_", "-")
    aliases = {
        "eng": "en", "en-us": "en", "en-gb": "en",
        "jpn": "ja", "jp": "ja",
        "spa": "es", "esp": "es",
        "fre": "fr", "fra": "fr",
        "ger": "de", "deu": "de",
        "ita": "it", "por": "pt",
        "kor": "ko", "chi": "zh", "zho": "zh",
        "rus": "ru", "ara": "ar", "hin": "hi",
    }
    return aliases.get(raw, raw.split("-", 1)[0] if raw else "")


def _audio_track_language(info: dict, track_number: int) -> str:
    track = next((item for item in info.get("audio_tracks", []) if int(item.get("track", 0)) == int(track_number)), {})
    language = _normalize_language_code(track.get("language"))
    title = str(track.get("title") or "").lower()
    if not language:
        if "english" in title or " dub" in f" {title}":
            return "en"
        if "japanese" in title or "日本" in title:
            return "ja"
    return language


def _choose_automatic_audio_track(info: dict) -> int:
    """Prefer an English track when one is clearly labelled; otherwise use default.

    The audio selector was intentionally removed from the public UI. This keeps dual-audio
    anime convenient without bringing that setting back.
    """
    tracks = info.get("audio_tracks", []) or []
    for item in tracks:
        lang = _normalize_language_code(item.get("language"))
        title = str(item.get("title") or "").lower()
        if lang == "en" or "english" in title or "eng dub" in title:
            return int(item.get("track") or 1)
    return int(info.get("default_audio_track") or (1 if tracks else 0))


def _validate_english_audio(info: dict, track_number: int) -> None:
    """Reject clearly-labelled non-English audio instead of producing misleading captions.

    Unknown/unlabelled streams are allowed because many ordinary English files have no
    language metadata. Dual-audio files still automatically prefer a labelled English dub.
    """
    language = _audio_track_language(info, track_number)
    if language and language not in {"en", "und", "unknown"}:
        label = language.upper()
        raise RuntimeError(
            f"Clip AI local transcription is English-only. The selected audio track is labelled {label}. "
            "Use an English dub/audio source for this video."
        )


def _trusted_speech_hint(subject_hint: str | None) -> str:
    # Only user-supplied context is trusted for speech vocabulary. Filenames are never
    # promoted into Whisper context because they can contain release-group noise or
    # words that are not actually spoken.
    clean = re.sub(r"\s+", " ", str(subject_hint or "")).strip(" .,_-")
    return clean[:160]


def _whisper_prompt(subject_hint: str | None, project_title: str | None = None) -> str | None:
    clean = _trusted_speech_hint(subject_hint)
    return f"{clean[:120]}." if clean else None


def _whisper_hotwords(subject_hint: str | None) -> str | None:
    """Return conservative proper-name vocabulary for faster-whisper when supported."""
    clean = _trusted_speech_hint(subject_hint)
    if not clean:
        return None
    # Keep the complete trusted label, plus meaningful constituent words. This helps
    # names such as "Attack on Titan" survive noisy dialogue without inventing terms.
    pieces = [clean]
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.-]{2,}", clean):
        if token.lower() not in {"the", "and", "for", "with", "from"} and token.lower() not in {p.lower() for p in pieces}:
            pieces.append(token)
    return ", ".join(pieces)[:220]


def _transcribe_chunk(chunk_path: str, offset_seconds: float, *, vad_filter: bool = True, cpu_threads: int | None = None, options: dict | None = None):
    backend = settings.transcription_backend.lower().strip()

    if backend == "local":
        from services.transcribe import transcribe_local_with_timestamps
        opts = dict(options or {})
        return transcribe_local_with_timestamps(
            chunk_path,
            model_name=str(opts.pop("model_name", settings.local_whisper_model)),
            device=settings.local_whisper_device,
            compute_type=settings.local_whisper_compute_type,
            offset_seconds=offset_seconds,
            vad_filter=vad_filter,
            cpu_threads=cpu_threads or settings.local_whisper_cpu_threads,
            **opts,
        )

    if backend == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when TRANSCRIPTION_BACKEND=openai.")
        from services.transcribe import transcribe_openai_with_timestamps
        return transcribe_openai_with_timestamps(
            chunk_path,
            settings.openai_api_key,
            model=settings.openai_transcribe_model,
            offset_seconds=offset_seconds,
        )

    raise RuntimeError("TRANSCRIPTION_BACKEND must be 'local' or 'openai'.")

def _transcription_strategy() -> str:
    backend = settings.transcription_backend.lower().strip()
    if backend == "local":
        return f"local:english-only:{settings.local_whisper_compute_type}:{TRANSCRIPTION_VERSION}"
    return f"openai:{settings.openai_transcribe_model}:word-v20.1"


def _is_memory_allocation_error(exc: BaseException) -> bool:
    """Recognize NumPy/faster-whisper allocation failures without importing NumPy internals."""
    if isinstance(exc, MemoryError):
        return True
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    return (
        "arraymemoryerror" in name
        or "unable to allocate" in text
        or "cannot allocate memory" in text
        or "failed to allocate memory" in text
        or "mkl_malloc" in text
        or "bad_alloc" in text
        or "bad allocation" in text
        or "not enough memory" in text
        or "out of memory" in text
    )


def _lower_memory_whisper_options(options: dict | None) -> dict | None:
    """Fall back from the stronger English model to tiny.en under RAM pressure."""
    if not options:
        return None
    current = str(options.get("model_name") or "").strip()
    lowered = dict(options)
    if current == settings.local_whisper_refine_model and settings.local_whisper_model != current:
        lowered["model_name"] = settings.local_whisper_model
        lowered["beam_size"] = 1
        lowered["condition_on_previous_text"] = False
        return lowered
    return None


def _transcribe_chunk_memory_safe(
    chunk_path: str,
    offset_seconds: float,
    *,
    vad_filter: bool,
    cpu_threads: int,
    split_seconds: int = 120,
    cancel_event=None,
    on_fallback=None,
    options: dict | None = None,
):
    """Transcribe a chunk and automatically retry NumPy STFT OOMs in smaller pieces.

    faster-whisper's NumPy STFT creates a temporary complex array proportional to
    audio duration. On memory-constrained Windows machines even a few-minute chunk
    can fail while the model, browser and web server are resident. Splitting only the
    failing chunk keeps timestamps accurate and avoids restarting the whole analysis.
    """
    try:
        kwargs = dict(
            offset_seconds=offset_seconds,
            vad_filter=vad_filter,
            cpu_threads=cpu_threads,
        )
        if options is not None:
            kwargs["options"] = options
        try:
            return _transcribe_chunk(chunk_path, **kwargs)
        except TypeError as type_exc:
            # Older test doubles / extension hooks may implement the pre-v23.4 helper
            # signature. Keep that compatibility without weakening the real path.
            if options is not None and "options" in str(type_exc) and "unexpected keyword" in str(type_exc):
                kwargs.pop("options", None)
                return _transcribe_chunk(chunk_path, **kwargs)
            raise
    except Exception as exc:
        if settings.transcription_backend.lower().strip() != "local" or not _is_memory_allocation_error(exc):
            raise

        # First recover from model-level memory pressure by dropping from base.en to
        # tiny.en before shortening the audio. The normal quality model is attempted first.
        active_options = options
        lower_options = _lower_memory_whisper_options(options)
        if lower_options is not None:
            try:
                from services.transcribe import clear_local_model_cache
                clear_local_model_cache()
            except Exception:
                pass
            gc.collect()
            retry_kwargs = dict(
                offset_seconds=offset_seconds,
                vad_filter=vad_filter,
                cpu_threads=max(1, min(int(cpu_threads), 2)),
                options=lower_options,
            )
            try:
                return _transcribe_chunk(chunk_path, **retry_kwargs)
            except Exception as lower_exc:
                if not _is_memory_allocation_error(lower_exc):
                    raise
                exc = lower_exc
                active_options = lower_options

        gc.collect()
        seconds = max(30, min(int(split_seconds), 120))
        if on_fallback is not None:
            on_fallback(seconds)

        source = Path(chunk_path)
        fallback_dir = source.parent / f"{source.stem}_memory_safe_{seconds}s"
        if fallback_dir.exists():
            shutil.rmtree(fallback_dir, ignore_errors=True)
        fallback_chunks = extract_audio_chunks(
            str(source),
            str(fallback_dir),
            chunk_seconds=seconds,
            cancel_event=cancel_event,
        )

        # If the smallest safe split still cannot reduce the input, surface a useful
        # message instead of recursively retrying forever.
        if len(fallback_chunks) <= 1 and seconds <= 30:
            raise RuntimeError(
                "Clip AI ran out of available RAM while preparing Whisper audio. "
                "Close memory-heavy apps, choose Low memory, and try again."
            ) from exc

        recovered: list[TranscriptSegment] = []
        next_split = max(30, seconds // 2)
        for index, subchunk in enumerate(fallback_chunks):
            if cancel_event is not None and cancel_event.is_set():
                raise CancelledError()
            recovered.extend(
                _transcribe_chunk_memory_safe(
                    subchunk,
                    offset_seconds + index * seconds,
                    vad_filter=vad_filter,
                    cpu_threads=cpu_threads,
                    split_seconds=next_split,
                    cancel_event=cancel_event,
                    on_fallback=on_fallback,
                    options=active_options,
                )
            )
            gc.collect()
        return recovered


def _eta_text(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"about {max(1, seconds)} sec remaining"
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"about {minutes} min remaining"
    hours = minutes // 60
    remainder = minutes % 60
    return f"about {hours} hr {remainder} min remaining" if remainder else f"about {hours} hr remaining"


def _rank_segments(segments, max_clips: int, *, context=None, media_path=None, duration_preference: str = "auto"):
    backend = settings.ranking_backend.lower().strip()

    if backend == "local":
        if context is None:
            from services.local_rank import rank_clip_candidates_local
            return rank_clip_candidates_local(segments, max_clips=max_clips)
        shots = []
        if media_path and (context.resolved_type in {"anime", "film-tv"} or context.resolved_structure == "compilation"):
            shots = detect_shot_boundaries(media_path)
        return rank_clip_candidates_m2(segments, max_clips=max_clips, context=context, shot_boundaries=shots, duration_preference=duration_preference)

    if backend == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when RANKING_BACKEND=openai.")
        from services.rank import rank_clip_candidates
        return rank_clip_candidates(
            segments=segments,
            api_key=settings.openai_api_key,
            model=settings.openai_rank_model,
            max_clips=max_clips,
        )

    raise RuntimeError("RANKING_BACKEND must be 'local' or 'openai'.")


def analyze_local_media(
    media_path: str,
    source_label: str,
    max_clips: int,
    *,
    job_id: str | None = None,
    project_title: str | None = None,
    source_type: str = "upload",
    author_name: str | None = None,
    thumbnail_url: str | None = None,
    processing_profile: str | None = None,
    content_type: str = "auto",
    content_structure: str = "auto",
    subject_hint: str | None = None,
    duration_preference: str = "auto",
    audio_track: int = 0,
    progress=None,
    cancel_event=None,
) -> AnalyzeResponse:
    resolved_job_id = job_id or str(uuid.uuid4())
    job_dir = _job_dir(resolved_job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = job_dir / "audio"
    profile = get_processing_profile(processing_profile or settings.processing_profile)
    requested_content_type = normalize_content_type(content_type)
    requested_content_structure = normalize_content_structure(content_structure)
    clean_subject_hint = normalize_subject_hint(subject_hint)
    duration_preference = (duration_preference or "auto").lower().strip()
    if duration_preference not in {"auto", "short", "balanced", "longer"}:
        duration_preference = "auto"
    audio_track = max(0, int(audio_track or 0))
    analysis_started = time.monotonic()
    transcription_seconds = 0.0
    ranking_seconds = 0.0
    metadata_seconds = 0.0
    transcript_source = "fresh"

    def notify(value: int, stage: str, message: str) -> None:
        if progress is not None:
            progress(value, stage, message)

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()

    try:
        check_cancel()
        notify(4, "Checking media", "Checking codecs, audio, duration and disk space…")
        detailed_info = probe_media(media_path)
        if not detailed_info.get("has_video"):
            raise RuntimeError("This file does not contain a readable video stream.")
        if not detailed_info.get("has_audio"):
            raise RuntimeError("This video has no audio track. Clip AI needs spoken audio to find clip moments.")
        audio_count = int(detailed_info.get("audio_streams") or 0)
        if audio_track > audio_count:
            raise RuntimeError(f"Audio track {audio_track} was selected, but this video only has {audio_count} audio track(s).")
        selected_audio_track = audio_track or _choose_automatic_audio_track(detailed_info)
        if audio_count > 1:
            track_info = next((item for item in detailed_info.get("audio_tracks", []) if int(item.get("track", 0)) == selected_audio_track), {})
            label_bits = [str(track_info.get("language") or "").upper(), str(track_info.get("title") or "")]
            track_label = " · ".join(bit for bit in label_bits if bit)
            notify(5, "Choosing audio", f"Using audio track {selected_audio_track} of {audio_count}{' · ' + track_label if track_label else ''}.")
        usage = shutil.disk_usage(Path(settings.work_dir).resolve())
        source_size = int(detailed_info.get("size_bytes") or 0)
        # Keep at least the configured floor plus enough room for a working copy/renders.
        required_free = max(int(settings.min_free_disk_gb * (1024 ** 3)), source_size * 2)
        if usage.free < required_free:
            raise RuntimeError(f"Not enough free disk space for safe processing. Free at least {required_free / (1024 ** 3):.1f} GB and try again.")

        working_media = media_path
        normalize_needed, normalize_reasons = should_normalize_media(detailed_info, media_path)
        if int(detailed_info.get("audio_streams") or 0) > 1:
            normalize_needed = True
            if "audio track selection" not in normalize_reasons:
                normalize_reasons.append("audio track selection")
        normalized_path = job_dir / "normalized.mp4"
        if normalize_needed:
            if normalized_path.exists() and normalized_path.stat().st_size > 0:
                notify(8, "Using normalized media", "Reusing the stable working copy created earlier.")
            else:
                notify(6, "Normalizing media", f"Creating a stable working copy ({', '.join(normalize_reasons)})…")
                normalize_media(media_path, str(normalized_path), cancel_event=cancel_event, preset=profile.render_preset, audio_track=selected_audio_track)
            working_media = str(normalized_path)

        duration = float(detailed_info.get("duration") or 0.0)
        effective_chunk_seconds = min(settings.audio_chunk_seconds, profile.chunk_seconds)
        if duration >= 1800:
            effective_chunk_seconds = min(effective_chunk_seconds, 300 if profile.name != "fast" else 480)
        if duration >= 2700:
            # Hour-ish sources are the highest-RAM path on typical 8 GB Windows PCs.
            # Smaller chunks reduce MKL/STFT spikes without forcing every short video
            # into the slower low-memory profile.
            long_cap = 120 if profile.name == "low-memory" else (180 if profile.name == "balanced" else 300)
            effective_chunk_seconds = min(effective_chunk_seconds, long_cap)

        save_project(job_dir, {
            "job_id": resolved_job_id,
            "title": project_title or Path(media_path).name,
            "source_type": source_type,
            "source_url": source_label if source_type == "youtube" else None,
            "author_name": author_name,
            "thumbnail_url": thumbnail_url,
            "status": "analyzing",
            "processing_profile": profile.name,
            "content_type": requested_content_type,
            "content_structure": requested_content_structure,
            "subject_hint": clean_subject_hint,
            "duration_preference": duration_preference,
            "media_preflight": detailed_info,
            "audio_track": selected_audio_track,
            "normalized": normalize_needed,
        })

        transcript_path = job_dir / "transcript.json"
        cache_root = Path(settings.work_dir) / "cache" / "transcripts"
        cache_key = transcript_cache_key(media_path, f"{_transcription_strategy()}:audio:{selected_audio_track}")
        segments: list[TranscriptSegment] = []

        existing_before_transcribe = load_project(job_dir) or {}
        transcript_is_current = str(existing_before_transcribe.get("transcription_version") or "") == TRANSCRIPTION_VERSION
        if transcript_path.exists() and transcript_is_current:
            try:
                raw = json.loads(transcript_path.read_text(encoding="utf-8"))
                segments = [TranscriptSegment.model_validate(item) for item in raw]
            except Exception:
                segments = []
            if segments:
                transcript_source = "saved-project"
                notify(64, "Using saved transcript", "This project already has the current quality transcript, so Clip AI skipped Whisper.")

        if not segments:
            cached = load_cached_transcript(cache_root, cache_key)
            if cached:
                segments = cached
                transcript_source = "cache"
                notify(64, "Using transcript cache", "This same video was transcribed before, so Clip AI reused the cached transcript.")

        detected_language = "en" if transcript_is_current else "unknown"
        language_confidence = 0.0
        translated_to_english = False
        transcript_quality_meta = dict(existing_before_transcribe.get("transcript_quality") or {}) if transcript_is_current else {}
        refined_chunks = int(existing_before_transcribe.get("transcript_refined_chunks") or 0) if transcript_is_current else 0

        if not segments:
            transcription_started = time.monotonic()
            notify(6, "Preparing audio", "Extracting lightweight 16 kHz mono speech audio…")
            if audio_dir.exists():
                shutil.rmtree(audio_dir, ignore_errors=True)
            chunks = extract_audio_chunks(
                working_media,
                str(audio_dir),
                chunk_seconds=effective_chunk_seconds,
                audio_track=1 if normalize_needed else selected_audio_track,
                cancel_event=cancel_event,
            )

            primary_options: dict = {}
            refine_options: dict = {}
            if settings.transcription_backend.lower().strip() == "local":
                from services.transcribe import choose_better_transcript, transcript_quality

                _validate_english_audio(detailed_info, selected_audio_track)
                detected_language = "en" if _audio_track_language(detailed_info, selected_audio_track) == "en" else "unknown"
                prompt = _whisper_prompt(clean_subject_hint, project_title or Path(media_path).stem)
                hotwords = _whisper_hotwords(clean_subject_hint)
                primary_english_model = (
                    settings.local_whisper_refine_model
                    if profile.name == "balanced"
                    else settings.local_whisper_model
                )
                primary_options = {
                    "model_name": primary_english_model,
                    "language": "en",
                    "task": "transcribe",
                    "initial_prompt": prompt,
                    "hotwords": hotwords,
                    "beam_size": 3 if profile.name == "balanced" else 1,
                    "condition_on_previous_text": True,
                }
                refine_options = {**primary_options, "model_name": settings.local_whisper_refine_model, "beam_size": 5}
                mode_label = "higher-accuracy" if profile.name == "balanced" else "fast"
                notify(12, "Speech ready", f"English transcription · {mode_label} pass with automatic accuracy rescue.")

            total_chunks = max(1, len(chunks))
            chunk_times: list[float] = []
            chunk_quality_scores: list[float] = []
            refined_chunks = 0
            for index, chunk_path in enumerate(chunks):
                check_cancel()
                pct = 18 + int((index / total_chunks) * 46)
                suffix = ""
                if chunk_times:
                    average = sum(chunk_times) / len(chunk_times)
                    suffix = f" · {_eta_text(average * (total_chunks - index))}"
                notify(pct, "Transcribing", f"Chunk {index + 1} of {total_chunks}{suffix}")
                started = time.monotonic()
                def memory_fallback(split_seconds: int) -> None:
                    notify(
                        pct,
                        "Reducing memory use",
                        f"Whisper needed more RAM. Retrying chunk {index + 1} in {split_seconds}-second pieces…",
                    )

                chunk_segments = _transcribe_chunk_memory_safe(
                    chunk_path,
                    offset_seconds=index * effective_chunk_seconds,
                    vad_filter=True,
                    cpu_threads=profile.cpu_threads,
                    split_seconds=min(120, max(60, effective_chunk_seconds // 2)),
                    cancel_event=cancel_event,
                    on_fallback=memory_fallback,
                    options=primary_options or None,
                )
                # VAD is excellent for speed but can reject quiet film dialogue/music-heavy
                # mixes. An empty chunk gets one automatic full-audio retry.
                if not chunk_segments and settings.transcription_backend.lower().strip() == "local":
                    notify(pct, "Retrying quiet audio", f"Chunk {index + 1} looked silent. Retrying without the speech filter…")
                    check_cancel()
                    chunk_segments = _transcribe_chunk_memory_safe(
                        chunk_path,
                        offset_seconds=index * effective_chunk_seconds,
                        vad_filter=False,
                        cpu_threads=profile.cpu_threads,
                        split_seconds=min(120, max(60, effective_chunk_seconds // 2)),
                        cancel_event=cancel_event,
                        on_fallback=memory_fallback,
                        options=primary_options or None,
                    )

                if chunk_segments and settings.transcription_backend.lower().strip() == "local":
                    quality = transcript_quality(chunk_segments)
                    if bool(quality.get("needs_refinement")):
                        notify(pct, "Improving transcript", f"Chunk {index + 1} had uncertain words. Running a focused accuracy pass…")
                        check_cancel()
                        refined = _transcribe_chunk_memory_safe(
                            chunk_path,
                            offset_seconds=index * effective_chunk_seconds,
                            vad_filter=True,
                            cpu_threads=profile.cpu_threads,
                            split_seconds=min(120, max(60, effective_chunk_seconds // 2)),
                            cancel_event=cancel_event,
                            on_fallback=memory_fallback,
                            options=refine_options or primary_options or None,
                        )
                        chunk_segments, quality, used_refinement = choose_better_transcript(chunk_segments, refined)
                        if used_refinement:
                            refined_chunks += 1
                    chunk_quality_scores.append(float(quality.get("score") or 0.0))

                chunk_times.append(max(0.01, time.monotonic() - started))
                segments.extend(chunk_segments)
                del chunk_segments
                gc.collect()
                completed_pct = 18 + int(((index + 1) / total_chunks) * 46)
                if index + 1 < total_chunks:
                    average = sum(chunk_times) / len(chunk_times)
                    notify(completed_pct, "Transcribing", f"Finished chunk {index + 1} of {total_chunks} · {_eta_text(average * (total_chunks - index - 1))}")

            if settings.transcription_backend.lower().strip() == "local":
                overall = transcript_quality(segments)
                transcript_quality_meta = dict(overall)
                if chunk_quality_scores:
                    transcript_quality_meta["average_chunk_score"] = round(sum(chunk_quality_scores) / len(chunk_quality_scores), 2)
                transcript_quality_meta["refined_chunks"] = refined_chunks
            transcription_seconds = max(0.0, time.monotonic() - transcription_started)

        check_cancel()
        if not segments:
            raise RuntimeError(
                "No usable speech could be transcribed. Clip AI retried without the silence filter; check that the dialogue is audible and not muted or extremely quiet."
            )

        notify(68, "Saving transcript", "Saving word-level timestamps and transcript cache…")
        transcript_path.write_text(
            json.dumps([segment.model_dump() for segment in segments], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        save_cached_transcript(cache_root, cache_key, segments)
        context = resolve_content_context(
            segments,
            requested_type=requested_content_type,
            requested_structure=requested_content_structure,
            subject_hint=clean_subject_hint,
            project_title=project_title or Path(media_path).name,
        )
        save_project(job_dir, {
            "status": "transcribed",
            "processing_profile": profile.name,
            "content_type": context.requested_type,
            "resolved_content_type": context.resolved_type,
            "content_structure": context.requested_structure,
            "resolved_content_structure": context.resolved_structure,
            "subject_hint": context.subject_hint,
            "duration_preference": duration_preference,
            "context_confidence": context.confidence,
            "context_signals": list(context.signals),
            "transcription_version": TRANSCRIPTION_VERSION,
            "transcript_language": detected_language or "unknown",
            "language_confidence": round(float(language_confidence or 0.0), 4),
            "translated_to_english": translated_to_english,
            "transcript_quality": transcript_quality_meta,
            "transcript_refined_chunks": refined_chunks,
        })

        check_cancel()
        existing_project = load_project(job_dir) or {}
        existing_clips = existing_project.get("clips") or []
        can_reuse_rank = (
            bool(existing_clips)
            and str(existing_project.get("duration_preference") or "auto") == duration_preference
            and str(existing_project.get("ranking_version") or "") == RANKING_VERSION
        )
        if can_reuse_rank and len(existing_clips) >= min(max_clips, len(existing_clips)):
            notify(78, "Using ranked moments", "Reusing the saved clip-ranking checkpoint…")
            clips = [ClipCandidate.model_validate(item) for item in existing_clips[:max_clips]]
        else:
            notify(74, "Finding moments", "Ranking the strongest standalone moments…")
            ranking_started = time.monotonic()
            if settings.ranking_backend.lower().strip() == "local":
                clips = _rank_segments(segments, max_clips=max_clips, context=context, media_path=working_media, duration_preference=duration_preference)
            else:
                clips = _rank_segments(segments, max_clips=max_clips)
            ranking_seconds = max(0.0, time.monotonic() - ranking_started)

        for clip in clips:
            previous = clip.context or {}
            clip.context = {**candidate_context(context, clip.start, clip.end,
                                               previous.get("scene_start"), previous.get("scene_end")), **previous}
        save_project(job_dir, {
            "status": "ranked",
            "clips": [clip.model_dump() for clip in clips],
            "ranking_version": RANKING_VERSION if settings.ranking_backend.lower().strip() == "local" else existing_project.get("ranking_version", "openai"),
            "processing_profile": profile.name,
            "content_type": context.requested_type,
            "resolved_content_type": context.resolved_type,
            "content_structure": context.requested_structure,
            "resolved_content_structure": context.resolved_structure,
            "subject_hint": context.subject_hint,
            "duration_preference": duration_preference,
            "context_confidence": context.confidence,
            "context_signals": list(context.signals),
        })

        notify(84, "Writing metadata", "Creating grounded titles, descriptions and useful tags…")
        metadata_started = time.monotonic()
        for idx, clip in enumerate(clips):
            check_cancel()
            dialogue = dialogue_for_range(segments, clip.start, clip.end)
            local_start = float((clip.context or {}).get("local_context_start", clip.start))
            local_end = float((clip.context or {}).get("local_context_end", clip.end))
            local_dialogue = dialogue_for_range(segments, local_start, local_end)
            generated = generate_clip_copy_local(
                dialogue or clip.hook,
                "auto",
                local_context=local_dialogue,
                subject_hint=context.subject_hint,
                content_type=context.resolved_type,
                moment_type=(clip.context or {}).get("moment_type"),
            )
            if settings.ranking_backend.lower().strip() == "local" or not clip.title.strip():
                clip.title = generated.title
            clip.description = generated.description
            clip.hashtags = list(generated.hashtags)
            clip.social_caption = generated.social_caption
            clip.context = {**(clip.context or {}), "grounded_terms": list(generated.grounded_terms), "copy_version": "q1"}
            if clips:
                notify(84 + int(((idx + 1) / len(clips)) * 8), "Writing metadata", f"Polishing clip {idx + 1} of {len(clips)}…")
        metadata_seconds = max(0.0, time.monotonic() - metadata_started)

        check_cancel()
        notify(94, "Saving project", "Saving the project so it can be reopened later…")
        save_project(
            job_dir,
            {
                "job_id": resolved_job_id,
                "title": project_title or Path(media_path).name,
                "source_type": source_type,
                "source_url": source_label if source_type == "youtube" else None,
                "author_name": author_name,
                "thumbnail_url": thumbnail_url,
                "clips": [clip.model_dump() for clip in clips],
                "status": "ready",
                "processing_profile": profile.name,
                "content_type": context.requested_type,
                "resolved_content_type": context.resolved_type,
                "content_structure": context.requested_structure,
                "resolved_content_structure": context.resolved_structure,
                "subject_hint": context.subject_hint,
                "duration_preference": duration_preference,
                "context_confidence": context.confidence,
                "context_signals": list(context.signals),
                "audio_track": selected_audio_track,
                "transcription_version": TRANSCRIPTION_VERSION,
                "transcript_language": detected_language or "unknown",
                "language_confidence": round(float(language_confidence or 0.0), 4),
                "translated_to_english": translated_to_english,
                "transcript_quality": transcript_quality_meta,
                "transcript_refined_chunks": refined_chunks,
                "performance": {
                    "analysis_seconds": round(max(0.0, time.monotonic() - analysis_started), 2),
                    "transcription_seconds": round(transcription_seconds, 2),
                    "ranking_seconds": round(ranking_seconds, 2),
                    "metadata_seconds": round(metadata_seconds, 2),
                    "transcript_source": transcript_source,
                },
            },
        )
        notify(98, "Cleaning up", "Removing temporary audio files…")
        if settings.cleanup_temp_audio and audio_dir.exists():
            shutil.rmtree(audio_dir, ignore_errors=True)

        return AnalyzeResponse(
            source_url=source_label,
            mock=False,
            clips=clips,
            job_id=resolved_job_id,
        )
    except CancelledError:
        try:
            save_project(job_dir, {"status": "cancelled", "processing_profile": profile.name})
        except Exception:
            pass
        if audio_dir.exists():
            shutil.rmtree(audio_dir, ignore_errors=True)
        raise
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        try:
            save_project(job_dir, {"status": "interrupted", "processing_profile": profile.name, "last_error": str(exc)})
        except Exception:
            pass
        if settings.cleanup_temp_audio and audio_dir.exists():
            shutil.rmtree(audio_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


def _system_preflight() -> SystemPreflightResponse:
    root = Path(settings.work_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    checks: list[SystemCheck] = []

    def add(check_id: str, label: str, ok: bool, detail: str, severity: str = "required"):
        checks.append(SystemCheck(id=check_id, label=label, ok=ok, detail=detail, severity=severity))

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    add("ffmpeg", "FFmpeg", bool(ffmpeg), ffmpeg or "FFmpeg is not available on PATH.")
    add("ffprobe", "FFprobe", bool(ffprobe), ffprobe or "FFprobe is not available on PATH.")

    try:
        probe = root / ".clipai-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        work_ok = True
        work_detail = f"Writable workspace: {root}"
    except OSError as exc:
        work_ok = False
        work_detail = f"Workspace is not writable: {exc}"
    add("workspace", "Local workspace", work_ok, work_detail)

    transcribe_backend = settings.transcription_backend.lower().strip()
    if transcribe_backend == "local":
        local_stt_ok = importlib.util.find_spec("faster_whisper") is not None
        add("transcription", "Local transcription", local_stt_ok, f"faster-whisper · {settings.local_whisper_model}" if local_stt_ok else "faster-whisper is not installed.")
    elif transcribe_backend == "openai":
        add("transcription", "OpenAI transcription", bool(settings.openai_api_key), "API key configured." if settings.openai_api_key else "OPENAI_API_KEY is missing.")
    else:
        add("transcription", "Transcription backend", False, f"Unknown backend: {settings.transcription_backend}")

    ranking_backend = settings.ranking_backend.lower().strip()
    if ranking_backend == "local":
        add("ranking", "Local clip ranking", True, "Local moment ranking is enabled.")
    elif ranking_backend == "openai":
        add("ranking", "OpenAI clip ranking", bool(settings.openai_api_key), "API key configured." if settings.openai_api_key else "OPENAI_API_KEY is missing.")
    else:
        add("ranking", "Ranking backend", False, f"Unknown backend: {settings.ranking_backend}")

    cv2_ok = importlib.util.find_spec("cv2") is not None
    add("vision", "Smart reframing", cv2_ok, "OpenCV is available." if cv2_ok else "OpenCV is not installed.", "warning")

    usage = shutil.disk_usage(root)
    free_gb = usage.free / (1024 ** 3)
    disk_ok = free_gb >= settings.min_free_disk_gb
    add("disk", "Free disk space", disk_ok, f"{free_gb:.1f} GB free.", "warning" if disk_ok else "required")

    project_count = 0
    project_storage = 0
    if root.exists():
        for job_dir in root.iterdir():
            if not job_dir.is_dir() or not (job_dir / "project.json").exists():
                continue
            project_count += 1
            project_storage += directory_size(job_dir)

    required_ok = all(item.ok for item in checks if item.severity == "required")
    privacy = (
        "Local transcription and ranking are enabled; source video processing stays on this PC."
        if transcribe_backend == "local" and ranking_backend == "local"
        else "One or more AI backends are configured to use an external API."
    )
    return SystemPreflightResponse(
        version=APP_VERSION,
        release=RELEASE_NAME,
        ready=required_ok,
        checks=checks,
        transcription_backend=settings.transcription_backend,
        ranking_backend=settings.ranking_backend,
        local_whisper_model=settings.local_whisper_model,
        work_dir=str(root),
        project_count=project_count,
        project_storage_bytes=project_storage,
        disk_free_bytes=usage.free,
        disk_total_bytes=usage.total,
        privacy_note=privacy,
    )


@app.get("/system/preflight", response_model=SystemPreflightResponse)
def system_preflight():
    return _system_preflight()


@app.post("/system/cleanup", response_model=CleanupResponse)
def system_cleanup():
    root = Path(settings.work_dir).resolve()
    before = directory_size(root)
    cleanup = cleanup_stale_work(root)
    cache_cleanup = cleanup_transcript_cache(root / "cache" / "transcripts")
    after = directory_size(root)
    return CleanupResponse(
        removed_files=int(cleanup.get("temp_files", 0)) + int(cleanup.get("audio_dirs", 0)) + int(cache_cleanup.get("removed_files", 0)),
        removed_bytes=max(0, before - after),
        startup_cleanup=int(STARTUP_CLEANUP.get("temp_files", 0)) + int(STARTUP_CLEANUP.get("audio_dirs", 0)),
    )


@app.get("/health")
def health():
    return {
        "ok": True,
        "version": APP_VERSION,
        "release": RELEASE_NAME,
        "mock_mode": settings.mock_mode,
        "transcription_backend": settings.transcription_backend,
        "ranking_backend": settings.ranking_backend,
        "local_whisper_model": settings.local_whisper_model,
        "api_key_configured": bool(settings.openai_api_key),
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "word_timestamps": True,
        "async_tasks": True,
        "cancellable_ffmpeg": True,
        "cleanup_temp_audio": settings.cleanup_temp_audio,
        "startup_cleanup": STARTUP_CLEANUP,
    }


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str):
    record = tasks.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskStatusResponse.model_validate(record)


@app.get("/tasks", response_model=list[TaskStatusResponse])
def task_history(limit: int = Query(default=50, ge=1, le=250)):
    return [TaskStatusResponse.model_validate(item) for item in tasks.list(limit)]


@app.post("/tasks/{task_id}/cancel", response_model=TaskStatusResponse)
def cancel_task(task_id: str):
    record = tasks.cancel(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskStatusResponse.model_validate(record)


@app.get("/youtube-info", response_model=YouTubeInfoResponse)
def youtube_info(url: str = Query(..., min_length=10, max_length=2048)):
    return fetch_youtube_info(url)


@app.post("/analyze-youtube-owned", response_model=AnalyzeResponse)
async def analyze_youtube_owned(
    source_url: str = Form(...),
    rights_confirmed: bool = Form(...),
    file: UploadFile = File(...),
    max_clips: int = Form(default=6),
    title: str | None = Form(default=None),
    author_name: str | None = Form(default=None),
    thumbnail_url: str | None = Form(default=None),
    processing_profile: str = Form(default="balanced"),
    content_type: str = Form(default="auto"),
    content_structure: str = Form(default="auto"),
    subject_hint: str | None = Form(default=None),
    duration_preference: str = Form(default="auto"),
    audio_track: int = Form(default=0),
):
    if not is_youtube_url(source_url):
        raise HTTPException(status_code=400, detail="Enter a valid YouTube URL.")
    if not rights_confirmed:
        raise HTTPException(status_code=422, detail="Confirm that you own this video or have permission to process it.")
    if max_clips < 1 or max_clips > 12:
        raise HTTPException(status_code=422, detail="max_clips must be between 1 and 12.")
    if settings.mock_mode:
        raise HTTPException(status_code=409, detail="Real analysis is disabled while MOCK_MODE=true.")

    filename = file.filename or "video.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Choose an MP4, MOV, MKV, WEBM, M4V or AVI source file.")

    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_path = job_dir / f"source{suffix}"

    try:
        with saved_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
    finally:
        await file.close()

    (job_dir / "youtube_source.json").write_text(
        json.dumps({"source_url": source_url, "source_filename": filename}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return analyze_local_media(
        str(saved_path),
        source_url,
        max_clips,
        job_id=job_id,
        project_title=title or filename,
        source_type="youtube",
        author_name=author_name,
        thumbnail_url=thumbnail_url,
        processing_profile=processing_profile,
        content_type=content_type,
        content_structure=content_structure,
        subject_hint=subject_hint,
        duration_preference=duration_preference,
        audio_track=audio_track,
    )


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):
    source_url = str(request.source_url)
    if not is_youtube_url(source_url):
        raise HTTPException(status_code=400, detail="Enter a YouTube URL.")

    if settings.mock_mode:
        return AnalyzeResponse(
            source_url=source_url,
            mock=True,
            clips=mock_clips(request.max_clips),
            job_id=None,
        )

    if not request.local_media_path:
        raise HTTPException(
            status_code=422,
            detail="Direct YouTube ingestion is not connected yet. Upload an authorised video file for real analysis.",
        )

    return analyze_local_media(request.local_media_path, source_url, request.max_clips, processing_profile=request.processing_profile, content_type=request.content_type, content_structure=request.content_structure, subject_hint=request.subject_hint, duration_preference=request.duration_preference, audio_track=request.audio_track)


@app.post("/tasks/analyze-upload", response_model=TaskCreateResponse, status_code=202)
async def start_analyze_upload_task(
    file: UploadFile = File(...),
    max_clips: int = Form(default=6),
    processing_profile: str = Form(default="balanced"),
    content_type: str = Form(default="auto"),
    content_structure: str = Form(default="auto"),
    subject_hint: str | None = Form(default=None),
    duration_preference: str = Form(default="auto"),
    audio_track: int = Form(default=0),
):
    if max_clips < 1 or max_clips > 12:
        raise HTTPException(status_code=422, detail="max_clips must be between 1 and 12.")
    if settings.mock_mode:
        raise HTTPException(status_code=409, detail="Real uploads are disabled while MOCK_MODE=true.")
    filename = file.filename or "video.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload MP4, MOV, MKV, WEBM, M4V or AVI video files.")

    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_path = job_dir / f"source{suffix}"
    try:
        with saved_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
    finally:
        await file.close()

    profile_name = get_processing_profile(processing_profile).name
    save_project(job_dir, {
        "job_id": job_id, "title": filename, "source_type": "upload",
        "clips": [], "status": "queued", "processing_profile": profile_name,
        "content_type": normalize_content_type(content_type),
        "content_structure": normalize_content_structure(content_structure),
        "duration_preference": duration_preference,
        "subject_hint": normalize_subject_hint(subject_hint),
        "audio_track": max(0, int(audio_track or 0)),
    })

    def runner(task_id, cancel_event):
        return analyze_local_media(
            str(saved_path), filename, max_clips,
            job_id=job_id, project_title=filename, source_type="upload", processing_profile=profile_name,
            content_type=content_type, content_structure=content_structure, subject_hint=subject_hint, duration_preference=duration_preference, audio_track=audio_track,
            progress=lambda pct, stage, message: tasks.progress(task_id, pct, stage, message),
            cancel_event=cancel_event,
        )

    record = tasks.create("analysis", runner, job_id=job_id, spec={"profile": profile_name, "max_clips": max_clips, "content_type": normalize_content_type(content_type), "content_structure": normalize_content_structure(content_structure), "subject_hint": normalize_subject_hint(subject_hint), "duration_preference": duration_preference, "audio_track": max(0, int(audio_track or 0))})
    return TaskCreateResponse(task_id=record["task_id"], job_id=job_id, status=record["status"])


@app.post("/tasks/analyze-youtube-owned", response_model=TaskCreateResponse, status_code=202)
async def start_analyze_youtube_task(
    source_url: str = Form(...),
    rights_confirmed: bool = Form(...),
    file: UploadFile = File(...),
    max_clips: int = Form(default=6),
    title: str | None = Form(default=None),
    author_name: str | None = Form(default=None),
    thumbnail_url: str | None = Form(default=None),
    processing_profile: str = Form(default="balanced"),
    content_type: str = Form(default="auto"),
    content_structure: str = Form(default="auto"),
    subject_hint: str | None = Form(default=None),
    duration_preference: str = Form(default="auto"),
    audio_track: int = Form(default=0),
):
    if not is_youtube_url(source_url):
        raise HTTPException(status_code=400, detail="Enter a valid YouTube URL.")
    if not rights_confirmed:
        raise HTTPException(status_code=422, detail="Confirm that you own this video or have permission to process it.")
    if max_clips < 1 or max_clips > 12:
        raise HTTPException(status_code=422, detail="max_clips must be between 1 and 12.")
    if settings.mock_mode:
        raise HTTPException(status_code=409, detail="Real analysis is disabled while MOCK_MODE=true.")

    filename = file.filename or "video.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Choose an MP4, MOV, MKV, WEBM, M4V or AVI source file.")

    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_path = job_dir / f"source{suffix}"
    try:
        with saved_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
    finally:
        await file.close()
    (job_dir / "youtube_source.json").write_text(
        json.dumps({"source_url": source_url, "source_filename": filename}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    profile_name = get_processing_profile(processing_profile).name
    save_project(job_dir, {
        "job_id": job_id, "title": title or filename, "source_type": "youtube", "source_url": source_url,
        "author_name": author_name, "thumbnail_url": thumbnail_url, "clips": [], "status": "queued",
        "processing_profile": profile_name,
        "content_type": normalize_content_type(content_type),
        "content_structure": normalize_content_structure(content_structure),
        "duration_preference": duration_preference,
        "subject_hint": normalize_subject_hint(subject_hint),
        "audio_track": max(0, int(audio_track or 0)),
    })

    def runner(task_id, cancel_event):
        return analyze_local_media(
            str(saved_path), source_url, max_clips,
            job_id=job_id, project_title=title or filename, source_type="youtube",
            author_name=author_name, thumbnail_url=thumbnail_url, processing_profile=profile_name,
            content_type=content_type, content_structure=content_structure, subject_hint=subject_hint, duration_preference=duration_preference, audio_track=audio_track,
            progress=lambda pct, stage, message: tasks.progress(task_id, pct, stage, message),
            cancel_event=cancel_event,
        )

    record = tasks.create("analysis", runner, job_id=job_id, spec={"profile": profile_name, "max_clips": max_clips, "content_type": normalize_content_type(content_type), "content_structure": normalize_content_structure(content_structure), "subject_hint": normalize_subject_hint(subject_hint), "duration_preference": duration_preference, "audio_track": max(0, int(audio_track or 0))})
    return TaskCreateResponse(task_id=record["task_id"], job_id=job_id, status=record["status"])


@app.post("/analyze-upload", response_model=AnalyzeResponse)
async def analyze_upload(
    file: UploadFile = File(...),
    max_clips: int = Form(default=6),
    processing_profile: str = Form(default="balanced"),
    content_type: str = Form(default="auto"),
    content_structure: str = Form(default="auto"),
    subject_hint: str | None = Form(default=None),
    duration_preference: str = Form(default="auto"),
    audio_track: int = Form(default=0),
):
    if max_clips < 1 or max_clips > 12:
        raise HTTPException(status_code=422, detail="max_clips must be between 1 and 12.")

    filename = file.filename or "video.mp4"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Upload MP4, MOV, MKV, WEBM, M4V or AVI video files.",
        )

    if settings.mock_mode:
        raise HTTPException(
            status_code=409,
            detail="Real uploads are disabled while MOCK_MODE=true. Set MOCK_MODE=false in apps/worker/.env and restart the worker.",
        )

    job_id = str(uuid.uuid4())
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_path = job_dir / f"source{suffix}"

    try:
        with saved_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                output.write(chunk)
    finally:
        await file.close()

    return analyze_local_media(
        str(saved_path),
        filename,
        max_clips,
        job_id=job_id,
        project_title=filename,
        source_type="upload",
        processing_profile=processing_profile,
        content_type=content_type,
        content_structure=content_structure,
        subject_hint=subject_hint,
        duration_preference=duration_preference,
        audio_track=audio_track,
    )


def _project_summary(job_dir: Path, data: dict) -> ProjectSummary:
    job_id = str(data.get("job_id") or job_dir.name)
    renders = rendered_media(job_dir, job_id)
    clips = data.get("clips") or []
    return ProjectSummary(
        job_id=job_id,
        title=str(data.get("title") or "Untitled project"),
        source_type="youtube" if data.get("source_type") == "youtube" else "upload",
        source_url=data.get("source_url"),
        author_name=data.get("author_name"),
        thumbnail_url=data.get("thumbnail_url"),
        created_at=str(data.get("created_at") or data.get("updated_at") or datetime.now(timezone.utc).isoformat()),
        updated_at=str(data.get("updated_at") or data.get("created_at") or datetime.now(timezone.utc).isoformat()),
        clip_count=len(clips),
        render_count=len(renders),
        storage_bytes=directory_size(job_dir),
        status=str(data.get("status") or "ready"),
        processing_profile=str(data.get("processing_profile") or "balanced"),
        content_type=str(data.get("content_type") or "auto"),
        resolved_content_type=str(data.get("resolved_content_type") or "other"),
        content_structure=str(data.get("content_structure") or "auto"),
        resolved_content_structure=str(data.get("resolved_content_structure") or "single-story"),
        subject_hint=data.get("subject_hint"),
        duration_preference=str(data.get("duration_preference") or "auto"),
        project_notes=str(data.get("project_notes") or ""),
        context_confidence=float(data.get("context_confidence") or 0.0),
        audio_track=int(data.get("audio_track") or 0),
        audio_track_count=int((data.get("media_preflight") or {}).get("audio_streams") or 0),
        source_available=source_available(job_dir),
        analysis_seconds=float((data.get("performance") or {}).get("analysis_seconds") or 0.0),
        transcript_language=str(data.get("transcript_language") or "unknown"),
        translated_to_english=bool(data.get("translated_to_english") or False),
        transcript_quality_score=float((data.get("transcript_quality") or {}).get("score") or 0.0),
    )


@app.get("/projects", response_model=list[ProjectSummary])
def list_projects():
    root = Path(settings.work_dir)
    if not root.exists():
        return []
    projects: list[ProjectSummary] = []
    for job_dir in root.iterdir():
        if not job_dir.is_dir() or not SAFE_ID.fullmatch(job_dir.name):
            continue
        data = load_project(job_dir)
        if data is None:
            continue
        projects.append(_project_summary(job_dir, data))
    projects.sort(key=lambda item: item.updated_at, reverse=True)
    return projects


@app.get("/projects/{job_id}", response_model=ProjectDetail)
def get_project(job_id: str):
    job_dir = _job_dir(job_id)
    data = load_project(job_dir)
    if data is None:
        raise HTTPException(status_code=404, detail="Saved project not found.")
    summary = _project_summary(job_dir, data)
    return ProjectDetail(
        **summary.model_dump(),
        clips=data.get("clips") or [],
        renders=rendered_media(job_dir, job_id),
    )



@app.post("/projects/{job_id}/cleanup", response_model=ProjectCleanupResponse)
def cleanup_project(job_id: str, request: ProjectCleanupRequest):
    job_dir = _job_dir(job_id)
    data = load_project(job_dir)
    if data is None:
        raise HTTPException(status_code=404, detail="Saved project not found.")
    if request.remove_source and not rendered_media(job_dir, job_id):
        raise HTTPException(status_code=409, detail="Render at least one finished video before deleting the source media.")
    result = cleanup_project_storage(job_dir, remove_source=request.remove_source)
    if request.remove_source:
        save_project(job_dir, {"source_archived": not bool(result["source_available"])})
    return ProjectCleanupResponse(**result)


@app.post("/projects/{job_id}/resume", response_model=TaskCreateResponse, status_code=202)
def resume_project(job_id: str):
    job_dir = _job_dir(job_id)
    data = load_project(job_dir)
    if data is None:
        raise HTTPException(status_code=404, detail="Saved project not found.")
    source = _find_source(job_id)
    profile_name = str(data.get("processing_profile") or settings.processing_profile)
    source_type = "youtube" if data.get("source_type") == "youtube" else "upload"
    source_label = str(data.get("source_url") or data.get("title") or source.name)
    max_clips = max(3, len(data.get("clips") or []) or 6)

    def runner(task_id, cancel_event):
        return analyze_local_media(
            str(source), source_label, max_clips,
            job_id=job_id,
            project_title=str(data.get("title") or source.name),
            source_type=source_type,
            author_name=data.get("author_name"),
            thumbnail_url=data.get("thumbnail_url"),
            processing_profile=profile_name,
            content_type=str(data.get("content_type") or "auto"),
            content_structure=str(data.get("content_structure") or "auto"),
            subject_hint=data.get("subject_hint"),
            duration_preference=str(data.get("duration_preference") or "auto"),
            audio_track=int(data.get("audio_track") or 0),
            progress=lambda pct, stage, message: tasks.progress(task_id, pct, stage, message),
            cancel_event=cancel_event,
        )

    record = tasks.create("analysis", runner, job_id=job_id, spec={"resume": True, "profile": profile_name})
    return TaskCreateResponse(task_id=record["task_id"], job_id=job_id, status=record["status"])


@app.patch("/projects/{job_id}/clips/{clip_index}/timing")
def update_clip_timing(job_id: str, clip_index: int, request: ClipTimingUpdateRequest):
    if request.end <= request.start:
        raise HTTPException(status_code=422, detail="Clip end must be greater than clip start.")
    if request.end - request.start > 180:
        raise HTTPException(status_code=422, detail="Clips are limited to 180 seconds.")
    job_dir, data, _clip = _saved_clip(job_id, clip_index)
    clips = list(data.get("clips") or [])
    clips[clip_index] = {**clips[clip_index], "start": round(request.start, 3), "end": round(request.end, 3)}
    save_project(job_dir, {**data, "clips": clips})
    return ClipCandidate.model_validate(clips[clip_index])


@app.get("/projects/{job_id}/transcript-range", response_model=TranscriptRangeResponse)
def transcript_range(job_id: str, start: float = Query(ge=0), end: float = Query(gt=0)):
    if end <= start:
        raise HTTPException(status_code=422, detail="end must be greater than start")
    segments = _load_transcript(job_id)
    selected = [s for s in segments if s.end >= start and s.start <= end]
    return TranscriptRangeResponse(start=start, end=end, text=" ".join(s.text.strip() for s in selected if s.text.strip()), segment_count=len(selected))


@app.patch("/projects/{job_id}/transcript-range", response_model=TranscriptRangeResponse)
def edit_transcript_range(job_id: str, request: TranscriptEditRequest):
    if request.end <= request.start:
        raise HTTPException(status_code=422, detail="end must be greater than start")
    transcript = _load_transcript(job_id)
    text = " ".join(request.text.split())
    keep = [s for s in transcript if s.end < request.start or s.start > request.end]
    new_segment = corrected_segment_with_preserved_timing(transcript, request.start, request.end, text)
    if new_segment is not None:
        keep.append(new_segment)
    keep.sort(key=lambda item: item.start)
    transcript_path = _job_dir(job_id) / "transcript.json"
    transcript_path.write_text(json.dumps([item.model_dump() for item in keep], ensure_ascii=False, indent=2), encoding="utf-8")
    project = load_project(_job_dir(job_id)) or {}
    try:
        transcript_revision = int(project.get("transcript_revision", 0)) + 1
    except (TypeError, ValueError):
        transcript_revision = 1
    save_project(
        _job_dir(job_id),
        {**project, "transcript_edited": True, "transcript_revision": transcript_revision},
    )
    return TranscriptRangeResponse(start=request.start, end=request.end, text=text, segment_count=1 if new_segment else 0)


@app.get("/projects/{job_id}/clips/{clip_index}/subtitles")
def export_subtitles(job_id: str, clip_index: int, format: str = Query(default="srt", pattern="^(srt|vtt)$")):
    _job_dir_value, _data, clip = _saved_clip(job_id, clip_index)
    transcript = _load_transcript(job_id)
    body = to_srt(transcript, clip.start, clip.end) if format == "srt" else to_vtt(transcript, clip.start, clip.end)
    media_type = "application/x-subrip" if format == "srt" else "text/vtt"
    return PlainTextResponse(body, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="clip-ai-{clip_index + 1}.{format}"'})


@app.post("/projects/{job_id}/cover")
def regenerate_cover(job_id: str, request: CoverRequest):
    if not SAFE_FILENAME.fullmatch(request.filename) or not request.filename.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Invalid render filename.")
    clips_dir = _job_dir(job_id) / "clips"
    source = clips_dir / request.filename
    if not source.exists():
        raise HTTPException(status_code=404, detail="Rendered Short not found.")
    cover_name = f"cover_custom_{Path(request.filename).stem}.jpg"
    cover_path = clips_dir / cover_name
    extract_cover_frame(str(source), str(cover_path), request.at_seconds)
    return {"cover_url": f"/media/{job_id}/{cover_name}", "at_seconds": request.at_seconds}


@app.get("/projects/{job_id}/clips/{clip_index}/export-package")
def export_package(job_id: str, clip_index: int, filename: str = Query(..., min_length=1, max_length=240)):
    job_dir, data, clip = _saved_clip(job_id, clip_index)
    if not SAFE_FILENAME.fullmatch(filename) or not filename.lower().endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Invalid render filename.")
    media = job_dir / "clips" / filename
    if not media.exists():
        raise HTTPException(status_code=404, detail="Rendered Short not found.")
    transcript = _load_transcript(job_id)
    exports = job_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    package_path = exports / f"{Path(filename).stem}-package.zip"
    metadata = {
        "schema": 1,
        "app": "Clip AI",
        "app_version": APP_VERSION,
        "project_id": job_id,
        "project_title": data.get("title"),
        "title": clip.title,
        "description": clip.description or "",
        "hashtags": clip.hashtags,
        "social_caption": clip.social_caption or "",
        "start": clip.start,
        "end": clip.end,
        "score": clip.score,
        "source_type": data.get("source_type"),
        "render_filename": filename,
        "transcript_revision": int(data.get("transcript_revision", 0) or 0),
        "content_type": data.get("resolved_content_type") or data.get("content_type") or "other",
        "content_structure": data.get("resolved_content_structure") or data.get("content_structure") or "single-story",
        "subject_hint": data.get("subject_hint"),
    }
    sidecar = media.with_suffix(".metadata.json")
    sidecar.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    custom_cover = job_dir / "clips" / f"cover_custom_{Path(filename).stem}.jpg"
    cover_candidates = ([custom_cover] if custom_cover.exists() else []) + sorted(
        (job_dir / "clips").glob(f"cover*_{round(clip.start*1000)}_{round(clip.end*1000)}.jpg"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(media, "short.mp4")
        zf.writestr("subtitles.srt", to_srt(transcript, clip.start, clip.end))
        zf.writestr("subtitles.vtt", to_vtt(transcript, clip.start, clip.end))
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        if cover_candidates:
            zf.write(cover_candidates[0], "cover.jpg")
    return FileResponse(package_path, media_type="application/zip", filename=f"{safe_download_name(clip.title)[:-4]}-package.zip")


@app.get("/system/diagnostics")
def diagnostic_export():
    root = Path(settings.work_dir).resolve()
    report_dir = root / "_diagnostics"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = report_dir / f"clip-ai-diagnostics-{stamp}.zip"
    build_diagnostic_zip(
        root, target,
        app_version=APP_VERSION,
        release_name=RELEASE_NAME,
        settings_summary={
            "transcription_backend": settings.transcription_backend,
            "ranking_backend": settings.ranking_backend,
            "local_whisper_model": settings.local_whisper_model,
            "processing_profile": settings.processing_profile,
            "audio_chunk_seconds": settings.audio_chunk_seconds,
            "cleanup_temp_audio": settings.cleanup_temp_audio,
        },
        tasks=tasks.list(100),
    )
    return FileResponse(target, media_type="application/zip", filename=target.name)


def _saved_clip(job_id: str, clip_index: int) -> tuple[Path, dict, ClipCandidate]:
    job_dir = _job_dir(job_id)
    data = load_project(job_dir)
    if data is None:
        raise HTTPException(status_code=404, detail="Saved project not found.")
    raw_clips = data.get("clips") or []
    if clip_index < 0 or clip_index >= len(raw_clips):
        raise HTTPException(status_code=404, detail="Saved clip not found.")
    return job_dir, data, ClipCandidate.model_validate(raw_clips[clip_index])


@app.post("/projects/{job_id}/clips/{clip_index}/generate-copy", response_model=ClipCopyResponse)
def generate_clip_copy(job_id: str, clip_index: int, request: ClipCopyGenerateRequest):
    job_dir, data, clip = _saved_clip(job_id, clip_index)
    transcript = _load_transcript(job_id)
    dialogue = dialogue_for_range(transcript, clip.start, clip.end)
    local_start = float((clip.context or {}).get("local_context_start", clip.start))
    local_end = float((clip.context or {}).get("local_context_end", clip.end))
    local_dialogue = dialogue_for_range(transcript, local_start, local_end)
    generated = generate_clip_copy_local(
        dialogue or clip.hook,
        request.style,
        local_context=local_dialogue,
        subject_hint=data.get("subject_hint"),
        content_type=data.get("resolved_content_type") or data.get("content_type"),
        moment_type=(clip.context or {}).get("moment_type"),
    )

    clips = list(data.get("clips") or [])
    clips[clip_index] = {
        **clips[clip_index],
        "title": generated.title,
        "description": generated.description,
        "hashtags": list(generated.hashtags),
        "social_caption": generated.social_caption,
        "context": {**(clips[clip_index].get("context") or {}), "grounded_terms": list(generated.grounded_terms), "copy_version": "q1"},
    }
    save_project(job_dir, {**data, "clips": clips})
    return ClipCopyResponse(
        clip_index=clip_index,
        title=generated.title,
        description=generated.description,
        hashtags=list(generated.hashtags),
        social_caption=generated.social_caption,
        style=generated.style,
    )


@app.patch("/projects/{job_id}/clips/{clip_index}/copy", response_model=ClipCopyResponse)
def update_clip_copy(job_id: str, clip_index: int, request: ClipCopyUpdateRequest):
    job_dir, data, _clip = _saved_clip(job_id, clip_index)
    title = request.title.strip()
    description = request.description.strip()
    hashtags = []
    for raw in request.hashtags:
        clean = re.sub(r"[^A-Za-z0-9]", "", raw.lstrip("#"))[:36]
        tag = f"#{clean}" if clean else ""
        if tag and tag.lower() not in {item.lower() for item in hashtags}:
            hashtags.append(tag)
        if len(hashtags) >= 7:
            break
    if not description and request.social_caption.strip():
        description = request.social_caption.strip().split("\n\n", 1)[0].strip()
    social_caption = f"{description}\n\n{' '.join(hashtags)}".strip() if hashtags else description
    if not title:
        raise HTTPException(status_code=422, detail="Title cannot be empty.")

    clips = list(data.get("clips") or [])
    clips[clip_index] = {
        **clips[clip_index],
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "social_caption": social_caption,
    }
    save_project(job_dir, {**data, "clips": clips})
    return ClipCopyResponse(
        clip_index=clip_index,
        title=title,
        description=description,
        hashtags=hashtags,
        social_caption=social_caption,
        style="auto",
    )


@app.patch("/projects/{job_id}/notes")
def update_project_notes(job_id: str, request: ProjectNotesUpdateRequest):
    job_dir = _job_dir(job_id)
    project = load_project(job_dir)
    if project is None:
        raise HTTPException(status_code=404, detail="Saved project not found.")
    saved = save_project(job_dir, {"project_notes": request.notes.strip()})
    return {"job_id": job_id, "notes": saved.get("project_notes") or ""}


@app.patch("/projects/{job_id}/clips/{clip_index}/feedback")
def update_clip_feedback(job_id: str, clip_index: int, request: ClipFeedbackRequest):
    job_dir = _job_dir(job_id)
    project = load_project(job_dir)
    if project is None:
        raise HTTPException(status_code=404, detail="Saved project not found.")
    clips = list(project.get("clips") or [])
    if clip_index < 0 or clip_index >= len(clips):
        raise HTTPException(status_code=404, detail="Clip suggestion not found.")
    clip = dict(clips[clip_index])
    context = dict(clip.get("context") or {})
    context["user_feedback"] = {"reason": request.reason, "note": request.note.strip()}
    clip["context"] = context
    clips[clip_index] = clip
    save_project(job_dir, {"clips": clips})
    return {"ok": True, "clip_index": clip_index, "feedback": context["user_feedback"]}


@app.delete("/projects/{job_id}")
def delete_project(job_id: str):
    job_dir = _job_dir(job_id)
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="Saved project not found.")
    shutil.rmtree(job_dir)
    return {"ok": True, "job_id": job_id}


def _render_clip_core(request: RenderClipRequest, *, progress=None, cancel_event=None) -> RenderClipResponse:
    if request.end <= request.start:
        raise HTTPException(status_code=422, detail="Clip end must be greater than clip start.")

    def notify(value: int, stage: str, message: str) -> None:
        if progress is not None:
            progress(value, stage, message)

    source = _find_source(request.job_id)
    job_dir = _job_dir(request.job_id)
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    start_ms = round(request.start * 1000)
    end_ms = round(request.end * 1000)
    filename = f"clip_{start_ms}_{end_ms}.mp4"
    output = clips_dir / filename

    try:
        if output.exists() and output.stat().st_size > 0:
            notify(94, "Using cached clip", "This clip was already rendered, so Clip AI reused it.")
        else:
            notify(15, "Cutting clip", "Encoding the selected timestamp range…")
            cut_clip(str(source), str(output), request.start, request.end, cancel_event=cancel_event)
            notify(92, "Finalizing", "Making the MP4 browser-friendly…")
    except CancelledError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Clip render failed: {exc}") from exc

    project = load_project(job_dir)
    if project is not None:
        save_project(job_dir, project)
        # Generic metadata sidecar: useful to any downstream publishing/archive tool.
        clip_match = next((item for item in (project.get("clips") or []) if abs(float(item.get("start", -1)) - request.start) < 0.05 and abs(float(item.get("end", -1)) - request.end) < 0.05), None)
        metadata = {
            "schema": 1, "app": "Clip AI", "app_version": APP_VERSION, "project_id": request.job_id,
            "project_title": project.get("title"), "render_filename": filename,
            "title": (clip_match or {}).get("title") or project.get("title") or "Clip AI Short",
            "description": (clip_match or {}).get("description") or "",
            "hashtags": (clip_match or {}).get("hashtags") or [],
            "social_caption": (clip_match or {}).get("social_caption") or "",
            "start": request.start, "end": request.end, "transcript_revision": int(project.get("transcript_revision", 0) or 0),
        }
        try:
            (clips_dir / f"{Path(filename).stem}.metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    media_url = f"/media/{request.job_id}/{filename}"
    return RenderClipResponse(
        job_id=request.job_id,
        filename=filename,
        start=round(request.start, 3),
        end=round(request.end, 3),
        duration=round(request.end - request.start, 3),
        media_url=media_url,
        download_url=f"{media_url}?download=true",
        kind="original",
    )


@app.post("/tasks/render-clip", response_model=TaskCreateResponse, status_code=202)
def start_render_clip_task(request: RenderClipRequest):
    def runner(task_id, cancel_event):
        return _render_clip_core(
            request,
            progress=lambda pct, stage, message: tasks.progress(task_id, pct, stage, message),
            cancel_event=cancel_event,
        )

    record = tasks.create("render", runner, job_id=request.job_id)
    return TaskCreateResponse(task_id=record["task_id"], job_id=request.job_id, status=record["status"])


@app.post("/render-clip", response_model=RenderClipResponse)
def render_clip(request: RenderClipRequest):
    return _render_clip_core(request)


def _render_short_core(request: RenderClipRequest, *, progress=None, cancel_event=None) -> RenderClipResponse:
    if request.end <= request.start:
        raise HTTPException(status_code=422, detail="Clip end must be greater than clip start.")

    def notify(value: int, stage: str, message: str) -> None:
        if progress is not None:
            progress(value, stage, message)

    def check_cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()

    source = _find_source(request.job_id)
    transcript = _load_transcript(request.job_id)
    render_start = request.start
    render_end = min(request.end, request.start + 9.0) if request.preview else request.end
    render_width, render_height = (540, 960) if request.preview else (720, 1280)
    job_dir = _job_dir(request.job_id)
    project_for_render = load_project(job_dir) or {}
    try:
        transcript_revision = max(0, int(project_for_render.get("transcript_revision", 0)))
    except (TypeError, ValueError):
        transcript_revision = 0
    clips_dir = job_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    resolved_content_type = str(
        project_for_render.get("resolved_content_type")
        or project_for_render.get("content_type")
        or "auto"
    ).lower().strip()
    start_ms = round(render_start * 1000)
    end_ms = round(render_end * 1000)
    content_tag = re.sub(r"[^a-z0-9]+", "-", resolved_content_type).strip("-") or "auto"
    plan_prefix = "reframe_v22_m5_preview" if request.preview else "reframe_v22_m5"
    plan_filename = f"{plan_prefix}_{content_tag}_{start_ms}_{end_ms}.json"
    plan_path = clips_dir / plan_filename

    try:
        check_cancel()
        if plan_path.exists():
            notify(22, "Loading framing", "Reusing the saved speaker-tracking plan…")
            reframe_plan = load_reframe_plan(plan_path)
        else:
            notify(8, "Scanning the scene", "Finding cuts, visual focus, faces and existing subtitles…")
            speech_intervals = [
                (segment.start, segment.end)
                for segment in transcript
                if segment.end >= render_start and segment.start <= render_end
            ]
            reframe_plan = plan_smart_reframe(
                str(source),
                render_start,
                render_end,
                target_width=render_width,
                target_height=render_height,
                speech_intervals=speech_intervals,
                content_type=resolved_content_type,
            )
            save_reframe_plan(reframe_plan, plan_path)
        check_cancel()
        notify(34, "Choosing layout", "Resolving Auto framing, video size and caption style…")

        layout_mode = choose_layout(request.layout_mode, reframe_plan, resolved_content_type)
        caption_style = choose_caption_style(request.caption_style, layout_mode, reframe_plan, resolved_content_type)
        frame_size = choose_frame_size(request.frame_size, layout_mode, reframe_plan, resolved_content_type)
        caption_zone = choose_caption_zone(caption_style, layout_mode, reframe_plan, resolved_content_type)
        resolved_profile = auto_profile(layout_mode, caption_style, reframe_plan, resolved_content_type)
        burned_in_subtitles = burned_subtitles_likely(reframe_plan)
        visual_warnings: list[str] = []
        if burned_in_subtitles:
            if resolved_content_type == "anime" and layout_mode == "focus" and caption_style == "cinematic":
                visual_warnings.append("Existing lower subtitles detected; Anime Cinematic keeps captions low, so review the preview for overlap.")
            else:
                visual_warnings.append("Existing lower subtitles detected; Clip AI moved its captions to a safer zone.")
        if reframe_plan.scene_cut_samples >= max(2, int(max(1, reframe_plan.sample_count) * 0.12)):
            visual_warnings.append("Frequent shot changes detected; framing resets at cuts instead of chasing the previous subject.")
        if resolved_content_type == "anime" and layout_mode == "preserve":
            visual_warnings.append("Anime composition preserved: more of the original frame stays visible.")

        offset_tag = f"p{request.caption_offset_ms}" if request.caption_offset_ms >= 0 else f"m{abs(request.caption_offset_ms)}"
        # Caption edits increment transcript_revision. Including it in the cache key ensures
        # an edited transcript never reuses a Short rendered with stale caption text.
        revision_tag = f"tr{transcript_revision}"
        prefix = "preview_v22m5" if request.preview else "short_v22m5"
        filename = f"{prefix}_{request.platform}_{layout_mode}_{frame_size}_{caption_style}_{caption_zone}_{offset_tag}_{revision_tag}_{start_ms}_{end_ms}.mp4"
        subtitle_filename = f"captions_{prefix}_{request.platform}_{layout_mode}_{frame_size}_{caption_style}_{caption_zone}_{offset_tag}_{revision_tag}_{start_ms}_{end_ms}.ass"
        output = clips_dir / filename
        subtitles = clips_dir / subtitle_filename

        notify(43, "Building captions", "Creating word-timed captions inside the video safe-zone…")
        _subtitle_path, word_timed = write_clip_ass(
            transcript,
            render_start,
            render_end,
            str(subtitles),
            caption_style=caption_style,
            layout_mode=layout_mode,
            frame_size=frame_size,
            width=render_width,
            height=render_height,
            caption_offset_ms=request.caption_offset_ms,
            caption_zone=caption_zone,
            platform=request.platform,
            content_type=resolved_content_type,
            source_width=reframe_plan.source_width,
            source_height=reframe_plan.source_height,
        )
        check_cancel()

        if output.exists() and output.stat().st_size > 0:
            notify(89, "Using cached Short", "This exact Short already exists, so Clip AI skipped encoding.")
        else:
            # Whisper/CTranslate2 is not needed for rendering. On 8 GB Windows machines the
            # cached speech model can otherwise leave x264 unable to allocate even a few MB.
            try:
                from services.transcribe import clear_local_model_cache
                clear_local_model_cache()
            except Exception:
                pass
            gc.collect()

            notify(55, "Rendering Short", "Encoding the vertical video. This is usually the longest step…")
            try:
                render_adaptive_short(
                    str(source), str(output), str(subtitles), render_start, render_end,
                    reframe_plan=reframe_plan, layout_mode=layout_mode, frame_size=frame_size,
                    width=render_width, height=render_height, cancel_event=cancel_event,
                )
            except CancelledError:
                raise
            except Exception as exc:
                if is_memory_allocation_error(exc):
                    check_cancel()
                    notify(64, "Freeing memory", "The encoder ran low on RAM. Retrying with a low-memory x264 configuration…")
                    try:
                        from services.transcribe import clear_local_model_cache
                        clear_local_model_cache()
                    except Exception:
                        pass
                    gc.collect()
                    render_adaptive_short(
                        str(source), str(output), str(subtitles), render_start, render_end,
                        reframe_plan=reframe_plan, layout_mode=layout_mode, frame_size=frame_size,
                        width=render_width, height=render_height,
                        encoder_preset="ultrafast", encoder_threads=1, cancel_event=cancel_event,
                    )
                else:
                    # Reliability fallback: if a dynamic tracking expression or unusual source
                    # breaks FFmpeg, retry once with a safe centered path instead of failing outright.
                    if reframe_plan.mode == "center":
                        raise
                    check_cancel()
                    notify(67, "Retrying safely", "The smart crop hit an encoding problem. Retrying with stable center framing…")
                    duration = max(0.05, render_end - render_start)
                    safe_plan = ReframePlan(
                        mode="center",
                        keyframes=[(0.0, 0.5), (duration, 0.5)],
                        source_width=reframe_plan.source_width,
                        source_height=reframe_plan.source_height,
                    )
                    render_adaptive_short(
                        str(source), str(output), str(subtitles), render_start, render_end,
                        reframe_plan=safe_plan, layout_mode=layout_mode, frame_size=frame_size,
                        width=render_width, height=render_height, cancel_event=cancel_event,
                    )
                    reframe_plan = safe_plan

        check_cancel()
        cover_filename = f"cover_v22m5_{request.platform}_{layout_mode}_{frame_size}_{caption_style}_{revision_tag}_{start_ms}_{end_ms}.jpg"
        cover_path = clips_dir / cover_filename
        if not request.preview and (not cover_path.exists() or cover_path.stat().st_size == 0):
            notify(92, "Creating cover", "Extracting a suggested cover frame…")
            cover_at = request.cover_offset_seconds if request.cover_offset_seconds is not None else max(0.15, (render_end - render_start) * 0.34)
            extract_cover_frame(str(output), str(cover_path), cover_at, cancel_event=cancel_event)
        notify(97, "Saving render" if not request.preview else "Preview ready", "Adding the finished Short to this project…" if not request.preview else "The quick preview is ready to check.")
    except CancelledError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Short render failed: {exc}") from exc

    project = load_project(job_dir)
    if project is not None and not request.preview:
        save_project(job_dir, project)
        # Generic metadata sidecar: useful to any downstream publishing/archive tool.
        clip_match = next((item for item in (project.get("clips") or []) if abs(float(item.get("start", -1)) - request.start) < 0.05 and abs(float(item.get("end", -1)) - request.end) < 0.05), None)
        metadata = {
            "schema": 1, "app": "Clip AI", "app_version": APP_VERSION, "project_id": request.job_id,
            "project_title": project.get("title"), "render_filename": filename,
            "title": (clip_match or {}).get("title") or project.get("title") or "Clip AI Short",
            "description": (clip_match or {}).get("description") or "",
            "hashtags": (clip_match or {}).get("hashtags") or [],
            "social_caption": (clip_match or {}).get("social_caption") or "",
            "start": request.start, "end": request.end, "transcript_revision": transcript_revision,
            "content_type": resolved_content_type, "layout_mode": layout_mode,
            "caption_style": caption_style, "caption_zone": caption_zone,
            "burned_in_subtitles": burned_in_subtitles,
            "visual_warnings": visual_warnings,
        }
        try:
            (clips_dir / f"{Path(filename).stem}.metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    media_url = f"/media/{request.job_id}/{filename}"
    return RenderClipResponse(
        job_id=request.job_id,
        filename=filename,
        start=round(render_start, 3),
        end=round(render_end, 3),
        duration=round(render_end - render_start, 3),
        media_url=media_url,
        download_url=f"{media_url}?download=true",
        kind="preview" if request.preview else "short",
        width=render_width,
        height=render_height,
        framing_mode=reframe_plan.mode,
        layout_mode=layout_mode,
        caption_style=caption_style,
        frame_size=frame_size,
        tracking_samples=reframe_plan.sample_count,
        face_samples=reframe_plan.face_samples,
        motion_samples=reframe_plan.motion_samples,
        active_speaker_samples=reframe_plan.active_speaker_samples,
        active_speaker_switches=reframe_plan.active_speaker_switches,
        group_fallback_samples=reframe_plan.group_fallback_samples,
        caption_offset_ms=request.caption_offset_ms,
        word_timed_captions=word_timed,
        caption_zone=caption_zone,
        platform=request.platform,
        cover_url=None if request.preview else f"/media/{request.job_id}/{cover_filename}",
        auto_profile=resolved_profile,
        saliency_samples=reframe_plan.saliency_samples,
        scene_cut_samples=reframe_plan.scene_cut_samples,
        subtitle_samples=reframe_plan.subtitle_samples,
        burned_in_subtitles=burned_in_subtitles,
        visual_warnings=visual_warnings,
    )


@app.post("/tasks/render-short", response_model=TaskCreateResponse, status_code=202)
def start_render_short_task(request: RenderClipRequest):
    def runner(task_id, cancel_event):
        return _render_short_core(
            request,
            progress=lambda pct, stage, message: tasks.progress(task_id, pct, stage, message),
            cancel_event=cancel_event,
        )

    record = tasks.create("render", runner, job_id=request.job_id)
    return TaskCreateResponse(task_id=record["task_id"], job_id=request.job_id, status=record["status"])


@app.post("/tasks/render-preview", response_model=TaskCreateResponse, status_code=202)
def start_render_preview_task(request: RenderClipRequest):
    preview_request = request.model_copy(update={"preview": True})
    def runner(task_id, cancel_event):
        return _render_short_core(
            preview_request,
            progress=lambda pct, stage, message: tasks.progress(task_id, pct, stage, message),
            cancel_event=cancel_event,
        )
    record = tasks.create("render-preview", runner, job_id=request.job_id)
    return TaskCreateResponse(task_id=record["task_id"], job_id=request.job_id, status=record["status"])


@app.post("/render-short", response_model=RenderClipResponse)
def render_short(request: RenderClipRequest):
    return _render_short_core(request)


@app.get("/media/{job_id}/{filename}")
def media_file(
    job_id: str,
    filename: str,
    download: bool = Query(default=False),
    name: str | None = Query(default=None, max_length=140),
):
    suffix = Path(filename).suffix.lower()
    if not SAFE_FILENAME.fullmatch(filename) or suffix not in {".mp4", ".jpg", ".jpeg", ".png"}:
        raise HTTPException(status_code=400, detail="Invalid media filename.")

    path = _job_dir(job_id) / "clips" / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Rendered media not found.")

    media_types = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    response_name = None
    if download:
        response_name = safe_download_name(name, path.stem) if suffix == ".mp4" else (name or path.name)
    return FileResponse(path, media_type=media_types[suffix], filename=response_name)
