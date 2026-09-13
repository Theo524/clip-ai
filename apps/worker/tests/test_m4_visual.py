from pathlib import Path

import cv2
import numpy as np

from models import TranscriptSegment, TranscriptWord
from services.captions import write_clip_ass
from services.layouts import (
    auto_profile,
    burned_subtitles_likely,
    choose_caption_style,
    choose_caption_zone,
    choose_frame_size,
    choose_layout,
    picture_window,
)
from services.reframe import (
    ReframePlan,
    _burned_subtitle_likelihood,
    _saliency_center,
    _stabilize_track_by_scenes,
)


def test_anime_auto_uses_familiar_cinematic_framing_and_captions():
    plan = ReframePlan(
        "saliency",
        [(0.0, 0.5)],
        1920,
        1080,
        sample_count=20,
        saliency_samples=18,
        scene_cut_samples=4,
    )
    layout = choose_layout("auto", plan, "anime")
    style = choose_caption_style("auto", layout, plan, "anime")
    assert layout == "focus"
    assert choose_frame_size("auto", layout, plan, "anime") == "compact"
    assert style == "cinematic"
    assert auto_profile(layout, style, plan, "anime") == "Anime · cinematic"



def test_anime_auto_compact_window_matches_requested_cinematic_height():
    # 800/1280 = 62.5% = 3.75 sixths of the vertical canvas.
    assert picture_window("focus", "compact", 1920, 1080, 720, 1280) == (0, 240, 720, 800)


def test_anime_cinematic_caption_stays_low_inside_compact_picture(tmp_path: Path):
    segments = [
        TranscriptSegment(
            start=0.0, end=1.0, text="Stay inside the frame",
            words=[
                TranscriptWord(start=0.0, end=0.2, text="Stay"),
                TranscriptWord(start=0.22, end=0.4, text="inside"),
                TranscriptWord(start=0.42, end=0.6, text="the"),
                TranscriptWord(start=0.62, end=0.9, text="frame"),
            ],
        )
    ]
    target = tmp_path / "anime_compact.ass"
    path, timed = write_clip_ass(
        segments, 0.0, 1.0, str(target),
        caption_style="cinematic", layout_mode="focus", frame_size="compact",
        caption_zone="lower", platform="tiktok", content_type="anime",
        source_width=1920, source_height=1080,
    )
    text = Path(path).read_text(encoding="utf-8-sig")
    assert timed
    # Picture is y=240..1040. 88% puts the anchor at y=944, low but still in-frame.
    assert "\\pos(360,944)" in text

def test_legacy_meme_caption_choice_maps_to_viral():
    plan = ReframePlan("face", [(0.0, 0.5)], 1920, 1080)
    assert choose_caption_style("meme", "fill", plan, "meme-comedy") == "viral"


def test_widescreen_preserve_picture_window_keeps_full_16_by_9_frame():
    assert picture_window("preserve", "balanced", 1920, 1080, 720, 1280) == (0, 437, 720, 405)


def test_existing_subtitles_move_auto_caption_zone_away_from_lower_band():
    plan = ReframePlan(
        "saliency",
        [(0.0, 0.5)],
        1920,
        1080,
        sample_count=10,
        subtitle_samples=5,
        subtitle_lower_samples=5,
    )
    assert burned_subtitles_likely(plan)
    assert choose_caption_zone("cinematic", "preserve", plan, "anime") == "middle"


def test_preserve_captions_stay_inside_actual_anime_picture(tmp_path: Path):
    segments = [
        TranscriptSegment(
            start=0.0,
            end=1.0,
            text="Keep the artwork visible",
            words=[
                TranscriptWord(start=0.0, end=0.2, text="Keep"),
                TranscriptWord(start=0.22, end=0.4, text="the"),
                TranscriptWord(start=0.42, end=0.65, text="artwork"),
                TranscriptWord(start=0.67, end=0.9, text="visible"),
            ],
        )
    ]
    target = tmp_path / "anime.ass"
    path, timed = write_clip_ass(
        segments,
        0.0,
        1.0,
        str(target),
        caption_style="cinematic",
        layout_mode="preserve",
        caption_zone="lower",
        content_type="anime",
        source_width=1920,
        source_height=1080,
    )
    text = Path(path).read_text(encoding="utf-8-sig")
    assert timed
    # 16:9 picture occupies y=437..842, so the lower caption anchor remains in-picture.
    assert "\\pos(360,781)" in text
    assert "Segoe UI Semibold,36" in text


def test_anime_cinematic_density_uses_shorter_phrases(tmp_path: Path):
    words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    transcript_words = [
        TranscriptWord(start=i * 0.2, end=i * 0.2 + 0.15, text=word)
        for i, word in enumerate(words)
    ]
    segments = [TranscriptSegment(start=0.0, end=2.2, text=" ".join(words), words=transcript_words)]
    target = tmp_path / "density.ass"
    path, _ = write_clip_ass(
        segments,
        0.0,
        2.2,
        str(target),
        caption_style="cinematic",
        content_type="anime",
    )
    dialogue_lines = [line for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.startswith("Dialogue:")]
    assert len(dialogue_lines) == 2


def test_burned_subtitle_heuristic_detects_synthetic_lower_text():
    frame = np.zeros((270, 480), dtype=np.uint8)
    cv2.putText(
        frame,
        "THE WORLD IS CHANGING",
        (60, 220),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        255,
        2,
        cv2.LINE_AA,
    )
    assert _burned_subtitle_likelihood(frame) >= 0.54


def test_saliency_fallback_finds_off_center_visual_interest():
    frame = np.zeros((270, 480), dtype=np.uint8)
    cv2.rectangle(frame, (340, 60), (450, 200), 255, -1)
    center, confidence = _saliency_center(frame)
    assert center > 0.70
    assert confidence > 0.03


def test_scene_cut_stabilization_does_not_drag_old_crop_into_new_shot():
    points = [
        (0.0, 0.30),
        (0.8, 0.30),
        (1.98, 0.30),
        (2.0, 0.70),
        (2.8, 0.70),
        (3.6, 0.70),
    ]
    stabilized = _stabilize_track_by_scenes(points, [2.0])
    new_shot = next(center for t, center in stabilized if t >= 2.0)
    assert new_shot >= 0.69


def test_reframe_round_trip_keeps_m4_visual_stats():
    plan = ReframePlan(
        "saliency",
        [(0.0, 0.5), (1.0, 0.55)],
        1920,
        1080,
        sample_count=12,
        saliency_samples=9,
        subtitle_samples=4,
        subtitle_lower_samples=4,
        scene_cut_samples=2,
        scene_cut_times=[0.4, 0.9],
        visual_profile="cinematic",
    )
    restored = ReframePlan.from_dict(plan.to_dict())
    assert restored.saliency_samples == 9
    assert restored.subtitle_samples == 4
    assert restored.scene_cut_times == [0.4, 0.9]
    assert restored.visual_profile == "cinematic"
