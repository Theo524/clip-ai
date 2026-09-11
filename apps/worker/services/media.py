from pathlib import Path
import shutil
import subprocess

from services.layouts import content_window, normalize_frame_size
from services.reframe import ReframePlan, build_crop_x_expression


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
    _run_render(command, target, "render the clip")
    return str(target)


def render_adaptive_short(
    media_path: str,
    output_path: str,
    subtitle_path: str,
    start: float,
    end: float,
    *,
    reframe_plan: ReframePlan,
    layout_mode: str,
    frame_size: str = "balanced",
    width: int = 720,
    height: int = 1280,
) -> str:
    """Create a 9:16 MP4 with a subject-aware content window and in-frame captions."""
    require_ffmpeg()

    source = Path(media_path)
    subtitles = Path(subtitle_path)
    if not source.exists():
        raise FileNotFoundError(f"Media file not found: {source}")
    if not subtitles.exists():
        raise FileNotFoundError(f"Caption file not found: {subtitles}")
    if start < 0:
        raise ValueError("Clip start must be zero or greater.")
    if end <= start:
        raise ValueError("Clip end must be greater than clip start.")

    duration = end - start
    if duration > 180:
        raise ValueError("Development clips are limited to 180 seconds.")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ass_name = subtitles.name.replace("'", "\\'")
    frame_size = normalize_frame_size(frame_size)

    if layout_mode == "fill":
        crop_x = build_crop_x_expression(reframe_plan)
        graph = (
            "[0:v]setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:x='{crop_x}':y='(ih-oh)/2',"
            f"ass='{ass_name}'[v]"
        )
    elif layout_mode in {"focus", "backdrop"}:
        win_x, win_y, win_w, win_h = content_window(frame_size, width, height)
        crop_x = build_crop_x_expression(reframe_plan)
        pad_color = "0x08080A"

        if layout_mode == "focus":
            # Large central content window (Balanced = 720x900 / 4:5) on a quiet
            # dark canvas. This is intentionally NOT a full 16:9 letterbox.
            graph = (
                "[0:v]setpts=PTS-STARTPTS,"
                f"scale={win_w}:{win_h}:force_original_aspect_ratio=increase,"
                f"crop={win_w}:{win_h}:x='{crop_x}':y='(ih-oh)/2',"
                f"pad={width}:{height}:{win_x}:{win_y}:color={pad_color},"
                f"ass='{ass_name}'[v]"
            )
        else:
            # Same central crop/window as Focus, with a subdued blurred copy behind it.
            # Captions are still drawn on the sharp video window, not the blur/margins.
            graph = (
                "[0:v]setpts=PTS-STARTPTS,split=2[bg][fg];"
                f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},gblur=sigma=28,eq=brightness=-0.22:saturation=0.72[bg2];"
                f"[fg]scale={win_w}:{win_h}:force_original_aspect_ratio=increase,"
                f"crop={win_w}:{win_h}:x='{crop_x}':y='(ih-oh)/2'[fg2];"
                f"[bg2][fg2]overlay={win_x}:{win_y}:format=auto,"
                f"ass='{ass_name}'[v]"
            )
    elif layout_mode == "preserve":
        pad_color = "0x08080A"
        graph = (
            "[0:v]setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={pad_color},"
            f"ass='{ass_name}'[v]"
        )
    else:
        raise ValueError(f"Unsupported layout mode: {layout_mode}")

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(source.resolve()),
        "-t", f"{duration:.3f}",
        "-filter_complex", graph,
        "-map", "[v]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        target.name,
    ]
    _run_render(command, target, f"render the {layout_mode} short", cwd=target.parent)
    return str(target)


def _run_render(command: list[str], target: Path, action: str, cwd: Path | None = None) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, cwd=str(cwd) if cwd else None)
    if completed.returncode != 0:
        detail = (completed.stderr or f"FFmpeg failed to {action}.").strip()
        raise RuntimeError(detail[-4000:])

    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg finished but no output file was produced while trying to {action}.")
