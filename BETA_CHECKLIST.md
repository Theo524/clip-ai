# Clip AI v21 long-term beta checklist

Use this checklist before treating v21 as the stable local build.

## Startup / first run
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
