from pathlib import Path
import subprocess


def extract_audio(media_path: str, output_path: str) -> str:
    """Extract mono 16 kHz audio suitable for transcription."""
    source = Path(media_path)
    if not source.exists():
        raise FileNotFoundError(f"Media file not found: {source}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg", "-y", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(out),
    ]
    subprocess.run(command, check=True, capture_output=True)
    return str(out)
