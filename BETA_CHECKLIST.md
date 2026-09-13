# Clip AI v22 M4 checkpoint checklist

Use this checklist before declaring M4 stable. Keep the M1-M3/v21 reliability checks below, especially render and recovery.

## M2 clip intelligence (test with a newly analyzed source)
- [ ] A comedy/meme source can produce a short complete 8–15 second moment; no forced 20–25 second padding.
- [ ] A longer answer/story can extend beyond 45 seconds when the ending needs it.
- [ ] A candidate does not stop at “but”, “because” or “and then”; listen for the answer or reaction after a short pause.
- [ ] On a mixed-scene compilation, a Best 3 clip never combines dialogue from unrelated scenes, and its opening makes sense on its own.
- [ ] Best 3 come from different good moments when available; Replace suggestion picks the next distinct candidate without another analysis.
- [ ] Render all 3 uses the currently displayed picks, including a replacement; Restore top picks returns to the first picks.
- [ ] Check any boundary/confidence warning against the actual source audio; manual trim still allows corrections.
- [ ] Reopen an older M1 project and confirm previous clip edits and renders remain unchanged.
- [ ] Time one 20–25 minute anime/film source on Balanced to check that optional shot cues do not slow the normal workflow excessively.

## Startup / first run
- [ ] In `apps\web`, `npm run build` completes on Windows (the build could not complete in the sandboxed validation environment).
- [ ] `CHECK_CLIP_AI.bat` reports FFmpeg, FFprobe, Node and the worker virtual environment correctly.
- [ ] `START_CLIP_AI.bat` opens worker + web terminals and then the app.
- [ ] System shows the required checks as Ready.
- [ ] Redacted diagnostics downloads successfully.

## Analysis / media preflight
- [ ] 2–5 minute talking-head MP4 completes.
- [ ] 15–25 minute mixed-content video completes.
- [ ] 30+ minute video shows useful chunk progress/ETA.
- [ ] A no-audio source fails early with a clear message.
- [ ] A quiet source exercises VAD fallback if needed.
- [ ] An unusual/VFR/rotated test source normalizes and then processes.
- [ ] Low memory, Balanced and Fast profiles can each start a job.
- [ ] Low disk-space protection gives a clear failure instead of filling the drive.

## Recovery / checkpoints
- [ ] Start a long analysis, close the worker, restart it, and confirm the interrupted project is marked recoverable.
- [ ] Resume that project and confirm completed transcription/ranking checkpoints are reused where applicable.
- [ ] Re-upload/reprocess the same source and verify transcript cache reuse.
- [ ] Cancel during a long task and confirm no fake completed output appears.

## Results / editing
- [ ] Best 3 ordering and scores look sensible.
- [ ] Manual start/end trim saves and affects the next render.
- [ ] Load a transcript range, correct a word/name, save it, and re-render captions.
- [ ] Auto/Fill/Focus/Backdrop/Preserve layouts still behave correctly.
- [ ] Viral Pop/Cinematic/Clean/Meme captions remain inside the actual video window.
- [ ] Two-person active-speaker tracking does not constantly micro-pan.
- [ ] Cover-frame slider produces the selected cover.

## Export
- [ ] Normal MP4 download works.
- [ ] SRT export has clip-relative timestamps.
- [ ] VTT export has clip-relative timestamps.
- [ ] Export package contains MP4 + subtitles + metadata + cover when available.
- [ ] Generic `.metadata.json` exists beside a rendered Short and contains the saved title/caption.

## Projects
- [ ] Search finds a project by title.
- [ ] Status/source filters work.
- [ ] Recoverable project exposes Resume.
- [ ] Old v20-era project opens after migration without losing renders/transcript.
- [ ] Deleting a disposable project removes its project storage only.

## Cleanup / regressions
- [ ] Clean temporary files leaves finished projects/renders intact.
- [ ] Backend test suite passes.
- [ ] Frontend core TSX syntax/transpilation check passes.

## M4 visual / anime checks

- [ ] Anime + Auto resolves to Preserve frame + Cinematic captions.
- [ ] Widescreen anime shows the full composition rather than a tight face crop.
- [ ] Cinematic captions sit low inside the picture, not in the black bar.
- [ ] A clip with existing lower subtitles moves Clip AI captions upward and shows a warning.
- [ ] Rapid anime/film cuts do not drag the previous face position into the next shot.
- [ ] Podcast/talking-head footage still follows a clearly active speaker when appropriate.
- [ ] Viral appears as one style in the UI; old projects saved as Meme still render.
- [ ] TikTok / Shorts / Reels lower safe-zone nudges still work.
