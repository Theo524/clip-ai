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
