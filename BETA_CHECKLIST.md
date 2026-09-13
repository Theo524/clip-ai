# Clip AI v22 Long-Term Beta freeze checklist

Use this before calling M6 stable on Windows.

## Core smoke test
- [ ] `npm run build` completes.
- [ ] `START_CLIP_AI.bat` starts worker + web and opens the app.
- [ ] System page is Ready.
- [ ] Backend suite reports 92 passed.

## Anime / captions
- [ ] Anime + Auto uses true-black 9:16 background with the Compact central picture (not tiny Preserve framing).
- [ ] Cinematic captions sit low **inside** the anime picture, not in the middle and not in the black bars.
- [ ] Quick Preview matches final framing closely.
- [ ] Rapid scene cuts do not drag the previous crop into the next shot.

## Clip intelligence / metadata
- [ ] Best 3 are distinct when good distinct scenes exist.
- [ ] A selected clip does not end mid-sentence / on “but”, “because”, “and then” when a natural continuation exists.
- [ ] Longer documentary/podcast moments can exceed short-form default duration when context needs it.
- [ ] Titles are headlines, not random transcript fragments.
- [ ] Description/tags match the selected local scene and do not invent unsupported names.

## Dual-audio media
- [ ] Normal single-audio MP4 works with Audio track = Auto.
- [ ] Dual-audio anime works with Auto when the desired track is default.
- [ ] Selecting Track 2 transcribes Track 2 and the final rendered Short uses that same audio.
- [ ] Selecting a nonexistent track fails early with a clear error.

## Recovery / performance
- [ ] 20–30 minute source completes on Balanced without the NumPy allocation crash.
- [ ] Interrupted project can still resume while source media exists.
- [ ] Saved transcript/cache reuse avoids rerunning Whisper when appropriate.
- [ ] Projects page shows a sensible analysis duration after a fresh run.

## Cleanup
- [ ] System cleanup removes stale temp/cache items without deleting finished projects.
- [ ] A project with no finished render cannot delete its source using Free space.
- [ ] A project with a finished render can use Free space; final MP4/transcript/metadata/export remain.
- [ ] After Free space, the project clearly shows that source media was cleaned and does not pretend it can re-render.

## Export / project durability
- [ ] MP4 download works.
- [ ] SRT/VTT export works.
- [ ] Export package contains MP4 + subtitle files + metadata + cover where available.
- [ ] Old v21/v22 projects migrate to schema 24 without losing renders/transcript.
