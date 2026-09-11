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
