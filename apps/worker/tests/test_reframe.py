import math
import numpy as np

from services.reframe import ReframePlan, _relative_mouth_activity, _speech_active
from services.layouts import auto_profile


def test_reframe_plan_round_trip_keeps_speaker_stats():
    plan = ReframePlan(
        mode="speaker",
        keyframes=[(0.0, 0.3), (1.0, 0.7)],
        source_width=1920,
        source_height=1080,
        sample_count=20,
        face_samples=18,
        multi_face_samples=14,
        active_speaker_samples=9,
        active_speaker_switches=2,
        group_fallback_samples=4,
        speaker_hold_samples=3,
    )
    restored = ReframePlan.from_dict(plan.to_dict())
    assert restored.mode == "speaker"
    assert restored.active_speaker_samples == 9
    assert restored.active_speaker_switches == 2
    assert restored.group_fallback_samples == 4
    assert restored.speaker_hold_samples == 3


def test_speech_active_uses_transcript_intervals():
    intervals = [(10.0, 12.0), (15.0, 16.0)]
    assert _speech_active(11.0, intervals)
    assert _speech_active(12.08, intervals)  # small tolerance
    assert not _speech_active(13.0, intervals)
    assert _speech_active(99.0, None)


def test_relative_mouth_activity_prefers_lower_face_motion():
    previous = np.zeros((100, 100), dtype=np.uint8)
    current = previous.copy()
    # Face box: x=20,y=10,w=60,h=80. Change only the lower/mouth region.
    current[55:82, 28:72] = 120
    score = _relative_mouth_activity(current, previous, 20, 10, 60, 80)
    assert score > 0.05


def test_relative_mouth_activity_ignores_upper_only_motion():
    previous = np.zeros((100, 100), dtype=np.uint8)
    current = previous.copy()
    current[28:48, 28:72] = 140
    score = _relative_mouth_activity(current, previous, 20, 10, 60, 80)
    assert score == 0.0


def test_auto_profile_reports_active_speaker_dialogue():
    plan = ReframePlan(
        mode="speaker",
        keyframes=[(0.0, 0.5)],
        source_width=1920,
        source_height=1080,
        active_speaker_samples=5,
        active_speaker_switches=1,
    )
    assert auto_profile("focus", "cinematic", plan) == "Active-speaker dialogue"


def test_long_reframe_expression_is_compressed_for_ffmpeg():
    from services.reframe import ReframePlan, build_crop_x_expression

    keyframes = [
        (index * 0.45, 0.5 + 0.20 * math.sin(index / 5.0))
        for index in range(120)
    ]
    expression = build_crop_x_expression(
        ReframePlan("speaker", keyframes, 1920, 1080)
    )

    # Keep comfortably below the FFmpeg expression nesting depth that fails around
    # ~100 nested if() calls on common builds.
    assert expression.count("if(") <= 71
    assert len(expression) < 7000


def test_reframe_keyframe_compression_keeps_endpoints():
    from services.reframe import _compress_keyframes

    points = [(index * 0.45, 0.3 + (index % 7) * 0.05) for index in range(120)]
    compressed = _compress_keyframes(points, max_points=72)

    assert len(compressed) <= 72
    assert compressed[0] == points[0]
    assert compressed[-1] == points[-1]


def test_camera_stabilizer_ignores_small_face_wobble():
    from services.reframe import _stabilize_camera_track

    points = [
        (0.0, 0.50),
        (0.5, 0.53),
        (1.0, 0.47),
        (1.5, 0.54),
        (2.0, 0.49),
        (2.5, 0.52),
    ]
    stabilized = _stabilize_camera_track(points)

    assert all(abs(center - 0.50) < 0.001 for _t, center in stabilized)


def test_camera_stabilizer_ignores_single_tracking_spike():
    from services.reframe import _stabilize_camera_track

    points = [(0.0, 0.50), (0.5, 0.50), (1.0, 0.61), (1.5, 0.50), (2.0, 0.50)]
    stabilized = _stabilize_camera_track(points)

    assert max(abs(center - 0.50) for _t, center in stabilized) < 0.001


def test_camera_stabilizer_moves_for_sustained_large_shift():
    from services.reframe import _stabilize_camera_track

    points = [
        (0.0, 0.50),
        (0.5, 0.50),
        (1.0, 0.66),
        (1.5, 0.68),
        (2.0, 0.69),
        (2.5, 0.70),
    ]
    stabilized = _stabilize_camera_track(points)

    assert stabilized[-1][1] > 0.56
    assert stabilized[-1][1] < 0.70  # corrects without chasing the face dead-centre
