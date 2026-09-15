from models import TranscriptSegment
from services.context import resolve_content_context
from services.smart_rank import rank_clip_candidates_m2


def seg(start, end, text):
    return TranscriptSegment(start=start, end=end, text=text)


def ctx(segments, content_type="anime", structure="single-story"):
    return resolve_content_context(
        segments,
        requested_type=content_type,
        requested_structure=structure,
    )


def test_story_media_does_not_promote_a_tiny_fragment_when_context_continues():
    segments = [
        seg(0, 5, "The commander opened the letter and froze."),
        seg(5.1, 11, "It said the missing squad had been found alive."),
        seg(11.1, 19, "Everyone in the room realised the rescue mission could still work."),
        seg(23, 31, "The next scene begins with an unrelated training exercise."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "anime"))
    assert clips
    assert clips[0].end >= 19
    assert clips[0].end - clips[0].start >= 15


def test_meme_can_still_be_genuinely_short_when_the_joke_is_complete():
    segments = [
        seg(0, 4, "Why did the laptop go to therapy?"),
        seg(4.1, 9, "It had too many unresolved tabs!"),
        seg(14, 22, "Now we are talking about something unrelated."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "meme-comedy"))
    assert clips
    assert clips[0].end - clips[0].start < 12


def test_compilation_best_three_favour_different_scenes():
    segments = [
        seg(0, 8, "The hidden door opened and revealed the missing map."),
        seg(8.1, 16, "That was the proof the group needed to continue."),
        seg(22, 30, "Why can an octopus change colour so quickly?"),
        seg(30.1, 39, "Special skin cells let it change appearance almost instantly."),
        seg(46, 54, "The comedian promised this trick would never fail."),
        seg(54.1, 62, "Then the chair collapsed and everyone started laughing."),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "other", "compilation"))
    assert len(clips) >= 2
    scene_ids = [clip.context.get("scene_id") for clip in clips[:3]]
    assert len(set(scene_ids)) == len(scene_ids)


def test_selected_clips_record_quality_score():
    segments = [
        seg(0, 8, "Why did the researcher return to the cave?"),
        seg(8.1, 18, "Because a new sample changed the original conclusion."),
        seg(18.1, 28, "That result finally explained the unusual readings."),
    ]
    clips = rank_clip_candidates_m2(segments, 2, ctx(segments, "documentary"))
    assert clips
    quality = clips[0].context.get("selection_quality")
    assert isinstance(quality, int)
    assert 1 <= quality <= 99


def test_duplicate_topic_windows_are_not_all_returned():
    segments = [
        seg(0, 7, "The detective found a key under the desk."),
        seg(7.1, 14, "The key opened the locked drawer beside the window."),
        seg(14.1, 21, "Inside the drawer was the letter that solved the case."),
        seg(21.1, 28, "That letter was the proof the detective needed."),
        seg(35, 43, "Later the story moves to a completely different witness."),
        seg(43.1, 52, "The witness admits they were never at the station."),
    ]
    clips = rank_clip_candidates_m2(segments, 4, ctx(segments, "film-tv"))
    assert clips
    # The selector should not spend every slot on tiny variations of the drawer/letter moment.
    starts = [clip.start for clip in clips]
    assert len(starts) == len(set(starts))
    assert any(clip.start >= 34 for clip in clips)


def test_quality_pass_prefers_complete_candidate_over_warning_heavy_alternative():
    segments = [
        seg(0, 8, "The pilot thought the storm was moving away."),
        seg(8.1, 16, "But then the radar showed it turning directly toward them."),
        seg(16.1, 25, "That was why they diverted before the runway closed."),
        seg(30, 38, "Because"),
        seg(38.1, 46, "the next topic never really finishes"),
    ]
    clips = rank_clip_candidates_m2(segments, 3, ctx(segments, "film-tv"))
    assert clips
    assert clips[0].start < 1
    assert clips[0].context.get("narrative_completeness", 0) >= 80


def test_frontend_dependencies_are_pinned_for_stable_candidate():
    import json
    from pathlib import Path
    package = Path(__file__).resolve().parents[2] / "web" / "package.json"
    data = json.loads(package.read_text(encoding="utf-8"))
    assert data["dependencies"] == {
        "next": "16.3.5",
        "react": "19.3.0",
        "react-dom": "19.3.0",
    }
    assert all(value != "latest" for value in data["devDependencies"].values())


def test_frontend_release_labels_match_v23_candidate():
    from pathlib import Path
    page = Path(__file__).resolve().parents[2] / "web" / "app" / "page.tsx"
    text = page.read_text(encoding="utf-8")
    assert "v23 · M5 final quality" in text
    assert "Clip AI v23 · Final Quality Pass" in text
