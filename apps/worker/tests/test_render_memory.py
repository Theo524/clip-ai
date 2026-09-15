from pathlib import Path

from services import media
from services.reframe import ReframePlan


def test_x264_malloc_is_detected_as_memory_error():
    assert media.is_memory_allocation_error("x264 [error]: malloc of size 3582272 failed") is True
    assert media.is_memory_allocation_error("mkl_malloc: failed to allocate memory") is True
    assert media.is_memory_allocation_error("invalid crop expression") is False


def test_low_memory_encoder_uses_single_thread_ultrafast(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    subs = tmp_path / "captions.ass"
    target = tmp_path / "short.mp4"
    source.write_bytes(b"video")
    subs.write_text("[Script Info]\n", encoding="utf-8")
    seen = {}

    monkeypatch.setattr(media, "require_ffmpeg", lambda: None)

    def fake_run(command, target_path, action, **kwargs):
        seen["command"] = list(command)
        target_path.write_bytes(b"ok")

    monkeypatch.setattr(media, "_run_render", fake_run)
    plan = ReframePlan("center", [(0.0, 0.5), (10.0, 0.5)], 1920, 1080)
    media.render_adaptive_short(
        str(source), str(target), str(subs), 0.0, 10.0,
        reframe_plan=plan, layout_mode="focus", frame_size="compact",
        encoder_preset="ultrafast", encoder_threads=1,
    )
    command = seen["command"]
    assert command[command.index("-preset") + 1] == "ultrafast"
    assert command[command.index("-threads") + 1] == "1"
