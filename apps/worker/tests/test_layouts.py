from services.layouts import choose_caption_style, choose_caption_zone, choose_layout, content_window
from services.reframe import ReframePlan


def test_auto_layout_uses_focus_instead_of_letterboxed_widescreen():
    podcast = ReframePlan("face", [(0.0, 0.5)], 1920, 1080, sample_count=10, face_samples=8)
    movie = ReframePlan("center", [(0.0, 0.5)], 1920, 1080, sample_count=10, face_samples=1)
    dialogue = ReframePlan(
        "face", [(0.0, 0.5)], 1920, 1080,
        sample_count=10, face_samples=8, multi_face_samples=4,
    )
    gameplay = ReframePlan("motion", [(0.0, 0.5)], 1920, 1080, sample_count=10, motion_samples=6)
    portrait = ReframePlan("portrait", [(0.0, 0.5)], 720, 1280)

    assert choose_layout("auto", podcast) == "fill"
    assert choose_layout("auto", movie) == "focus"
    assert choose_layout("auto", dialogue) == "focus"
    assert choose_layout("auto", gameplay) == "backdrop"
    assert choose_layout("auto", portrait) == "preserve"
    assert choose_caption_style("auto", "focus", movie) == "cinematic"


def test_balanced_focus_window_is_centered_four_by_five():
    x, y, w, h = content_window("balanced", 720, 1280)
    assert (x, w, h) == (0, 720, 900)
    assert y == 190


def test_caption_zone_avoids_face_heavy_band():
    lower_face = ReframePlan(
        "face", [(0.0, 0.5)], 1920, 1080,
        sample_count=10, face_samples=8, face_lower_samples=7, face_middle_samples=1,
    )
    middle_face = ReframePlan(
        "face", [(0.0, 0.5)], 1920, 1080,
        sample_count=10, face_samples=8, face_middle_samples=7, face_lower_samples=1,
    )
    no_faces = ReframePlan("center", [(0.0, 0.5)], 1920, 1080, sample_count=10)

    assert choose_caption_zone("cinematic", "focus", lower_face) == "middle"
    assert choose_caption_zone("viral", "fill", middle_face) == "lower"
    assert choose_caption_zone("cinematic", "focus", no_faces) == "lower"
    assert choose_caption_zone("viral", "fill", no_faces) == "middle"


def test_auto_frame_size_preserves_group_context():
    from services.layouts import choose_frame_size

    group_scene = ReframePlan(
        "face", [(0.0, 0.5)], 1920, 1080,
        sample_count=10, face_samples=8, multi_face_samples=4,
    )
    single_face = ReframePlan(
        "face", [(0.0, 0.5)], 1920, 1080,
        sample_count=10, face_samples=8, multi_face_samples=0,
    )

    assert choose_frame_size("auto", "focus", group_scene) == "compact"
    assert choose_frame_size("auto", "focus", single_face) == "balanced"
    assert choose_frame_size("immersive", "focus", group_scene) == "immersive"


def test_scene_cut_evidence_pushes_auto_toward_focus():
    cut_heavy = ReframePlan(
        "motion", [(0.0, 0.5)], 1920, 1080,
        sample_count=10, motion_samples=5, scene_cut_samples=3,
    )
    assert choose_layout("auto", cut_heavy) == "focus"
