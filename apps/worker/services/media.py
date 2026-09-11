from pathlib import Path
import shutil
import subprocess


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "FFmpeg was not found. Install FFmpeg and make sure 'ffmpeg -version' works in Command Prompt."
        )


def extract_audio_chunks(media_path: str, output_dir: str, chunk_seconds: int = 1200) -> list[str]:
    """Extract mono 16 kHz MP3 chunks suitable for timestamped transcription."""
    require_ffmpeg()

    source = Path(media_path)
    if not source.exists():
        raise FileNotFoundError(f"Media file not found: {source}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "audio_%03d.mp3"

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k",
        "-f", "segment", "-segment_time", str(chunk_seconds),
        "-reset_timestamps", "1", str(pattern),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or "FFmpeg failed to extract audio.").strip()
        raise RuntimeError(detail[-2000:])

    chunks = sorted(str(path) for path in out_dir.glob("audio_*.mp3"))
    if not chunks:
        raise RuntimeError("FFmpeg did not produce any audio chunks.")
    return chunks


def cut_clip(media_path: str, output_path: str, start: float, end: float) -> str:
    """Render a broadly compatible MP4 for one selected timestamp range."""
    require_ffmpeg()

    source = Path(media_path)
    if not source.exists():
        raise FileNotFoundError(f"Media file not found: {source}")

    if start < 0:
        raise ValueError("Clip start must be zero or greater.")
    if end <= start:
        raise ValueError("Clip end must be greater than clip start.")

    duration = end - start
    if duration > 180:
        raise ValueError("Development clips are limited to 180 seconds.")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Re-encode instead of stream-copying so cuts are frame-accurate and the result
    # plays reliably in browsers even when the source uses an awkward codec/keyframe layout.
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(source),
        "-t", f"{duration:.3f}",
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or "FFmpeg failed to render the clip.").strip()
        raise RuntimeError(detail[-3000:])

    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError("FFmpeg finished but no clip file was produced.")

    return str(target)
