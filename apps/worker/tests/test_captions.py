from pathlib import Path

from models import TranscriptSegment, TranscriptWord
from services.captions import write_clip_ass


def test_word_timed_viral_captions_use_one_layer_without_ghost_text(tmp_path: Path):
    segments = [
        TranscriptSegment(
            start=10.0,
            end=11.5,
            text="This really works",
            words=[
                TranscriptWord(start=10.0, end=10.3, text="This"),
                TranscriptWord(start=10.35, end=10.8, text="really"),
                TranscriptWord(start=10.85, end=11.3, text="works"),
            ],
        )
    ]
    target = tmp_path / "captions.ass"
    path, word_timed = write_clip_ass(
        segments,
        10.0,
        12.0,
        str(target),
        caption_style="viral",
        layout_mode="focus",
        caption_zone="middle",
    )

    text = Path(path).read_text(encoding="utf-8-sig")
    assert word_timed is True
    dialogue_lines = [line for line in text.splitlines() if line.startswith("Dialogue:")]
    assert len(dialogue_lines) == 3
    assert all(line.startswith("Dialogue: 0,") for line in dialogue_lines)
    assert all("\\fad(" not in line for line in dialogue_lines)
    assert all("\\move(" not in line for line in dialogue_lines)
    assert all("\\alpha&HFF&" not in line for line in dialogue_lines)
    assert all("This" in line and "really" in line and "works" in line for line in dialogue_lines)
    assert any("\\fscx108" in line for line in dialogue_lines)

def test_caption_offset_moves_word_timing(tmp_path: Path):
    segments = [
        TranscriptSegment(
            start=5.0,
            end=6.0,
            text="Hello there",
            words=[
                TranscriptWord(start=5.0, end=5.4, text="Hello"),
                TranscriptWord(start=5.5, end=5.9, text="there"),
            ],
        )
    ]
    target = tmp_path / "offset.ass"
    path, word_timed = write_clip_ass(
        segments,
        5.0,
        7.0,
        str(target),
        caption_style="cinematic",
        caption_offset_ms=200,
    )
    text = Path(path).read_text(encoding="utf-8-sig")
    assert word_timed is True
    assert "0:00:00.20" in text


def test_focus_caption_position_stays_inside_video_window(tmp_path: Path):
    segments = [
        TranscriptSegment(
            start=0.0,
            end=1.0,
            text="Stay inside",
            words=[
                TranscriptWord(start=0.0, end=0.4, text="Stay"),
                TranscriptWord(start=0.45, end=0.9, text="inside"),
            ],
        )
    ]
    target = tmp_path / "zone.ass"
    path, _ = write_clip_ass(
        segments,
        0.0,
        1.0,
        str(target),
        caption_style="cinematic",
        layout_mode="focus",
        frame_size="balanced",
        caption_zone="lower",
    )
    text = Path(path).read_text(encoding="utf-8-sig")
    # Balanced video window is y=190..1090; lower 85% lands at y=955.
    assert "\\pos(360,955)" in text


def test_legacy_segment_transcript_still_renders(tmp_path: Path):
    segments = [TranscriptSegment(start=0.0, end=2.0, text="Legacy timing still works")]
    target = tmp_path / "legacy.ass"
    path, word_timed = write_clip_ass(segments, 0.0, 2.0, str(target))
    text = Path(path).read_text(encoding="utf-8-sig")
    assert word_timed is False
    assert "Legacy timing" in text


def test_caption_phrasing_avoids_dangling_final_connector(tmp_path: Path):
    segments = [
        TranscriptSegment(
            start=0.0,
            end=3.0,
            text="I tried it and it actually worked",
            words=[
                TranscriptWord(start=0.0, end=0.3, text="I"),
                TranscriptWord(start=0.31, end=0.7, text="tried"),
                TranscriptWord(start=0.71, end=0.9, text="it"),
                TranscriptWord(start=0.91, end=1.05, text="and"),
                TranscriptWord(start=1.06, end=1.25, text="it"),
                TranscriptWord(start=1.26, end=1.8, text="actually"),
                TranscriptWord(start=1.81, end=2.3, text="worked"),
            ],
        )
    ]
    target = tmp_path / "phrasing.ass"
    path, timed = write_clip_ass(segments, 0.0, 3.0, str(target), caption_style="viral")
    text = Path(path).read_text(encoding="utf-8-sig")
    assert timed is True
    assert "and\\N" not in text
    assert "actually" in text


def test_tiktok_lower_safe_zone_moves_caption_up(tmp_path: Path):
    segments = [
        TranscriptSegment(
            start=0.0,
            end=1.0,
            text="Safe zone",
            words=[
                TranscriptWord(start=0.0, end=0.4, text="Safe"),
                TranscriptWord(start=0.45, end=0.9, text="zone"),
            ],
        )
    ]
    target = tmp_path / "tiktok.ass"
    path, _ = write_clip_ass(
        segments,
        0.0,
        1.0,
        str(target),
        caption_style="cinematic",
        layout_mode="focus",
        frame_size="balanced",
        caption_zone="lower",
        platform="tiktok",
    )
    text = Path(path).read_text(encoding="utf-8-sig")
    # Balanced window is y=190..1090; TikTok lower safe zone uses 77% -> 883.
    assert "\\pos(360,883)" in text
