from services.smart_rank import duration_bounds
from services.layouts import choose_caption_zone, content_window
from services.reframe import ReframePlan


def test_duration_preferences_shift_soft_bounds():
    assert duration_bounds("anime", "auto") == (15, 45)
    short = duration_bounds("anime", "short")
    longer = duration_bounds("anime", "longer")
    assert short[0] < 15 and short[1] < 45
    assert longer[0] >= 15 and longer[1] > 45


def test_anime_cinematic_forces_lower_zone_without_burned_subtitles():
    plan = ReframePlan("saliency", [(0.0, 0.5)], 1920, 1080, sample_count=10, face_lower_samples=10)
    assert choose_caption_zone("cinematic", "focus", plan, "anime") == "lower"


def test_preview_canvas_keeps_compact_proportion():
    assert content_window("compact", 540, 960) == (0, 180, 540, 600)


def test_render_request_supports_preview_flag():
    from models import RenderClipRequest
    request = RenderClipRequest(job_id="job", start=1.0, end=20.0, preview=True)
    assert request.preview is True


def test_preview_files_are_hidden_from_saved_render_history(tmp_path):
    from services.projects import rendered_media
    clips = tmp_path / "clips"
    clips.mkdir()
    (clips / "preview_v22m5_test.mp4").write_bytes(b"x")
    (clips / "short_v22m5_test.mp4").write_bytes(b"x")
    items = rendered_media(tmp_path, "job")
    assert [item["filename"] for item in items] == ["short_v22m5_test.mp4"]
