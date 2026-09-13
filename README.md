# Clip AI v22 M3 · Titles & Social Metadata

Clip AI turns long English-language videos into ranked, reframed, captioned, ready-to-post vertical Shorts. M3 keeps the M2.1 memory-safe analysis pipeline and upgrades the copy/metadata layer so titles are more coherent and every selected clip can carry a grounded description and useful tags.

## v22 M3 highlights

- **Smarter titles:** Clip AI scores complete sentences for both interest and topical centrality instead of simply lifting a random catchy transcript line. Common dialogue patterns are rewritten into restrained headline forms without adding new facts.
- **Scene-local context:** title/description generation can use the nearby M2 scene envelope to understand the moment, but the output description itself stays grounded in the selected clip. Compilation clips do not borrow unrelated context from other scenes.
- **Show / program / subject grounding:** the optional subject hint is trusted user-provided context. It may appear in a concise title or tags when useful. Clip AI does not invent character/person names.
- **Description + tags:** each clip now has an editable description and up to seven hashtags. Tags combine known content type, moment type and a small number of grounded topic terms.
- **Publisher compatibility:** `social_caption` remains available as `description + tags`, so generic local publishing tools that already read Clip AI metadata continue to work.
- **Richer exports:** export packages and render sidecars include `description`, `hashtags`, title, timestamps, context and the legacy combined social caption.

## M2.1 intelligence and memory safety retained

- Transcript pauses, local topic shifts and compilation cues divide the source into independent scenes. Anime/film/compilation sources can use bounded FFmpeg keyframe cut hints.
- Candidates use content-type soft duration ranges and protect natural endings rather than forcing every clip to ~20–25 seconds.
- Best 3 favors distinct scenes; replacement suggestions reuse already-ranked candidates.
- Balanced uses 5-minute transcription chunks, Low memory 3-minute chunks and Fast 10-minute chunks. If faster-whisper hits a NumPy allocation error, Clip AI retries only the failing chunk in progressively smaller pieces.

## M1 context foundation retained

### Content context
Before analysis you can leave **Auto** selected or give Clip AI a content type, source structure and optional show/program/subject hint. Auto remains conservative. The resolved context is stored with the project and each candidate.

Compilation context is local by design: a show/topic hint may help future names and framing decisions, but does not tell Clip AI that every segment of a compilation is the same event.

## v21 foundation retained

### Recoverable long-video processing
- Persistent task history survives worker restarts.
- Interrupted projects are marked recoverable instead of disappearing.
- **Resume** reuses saved source media, transcript/ranking checkpoints and render caches where possible.
- Project metadata is migrated forward additively and saved atomically.
- Long jobs keep stage/status information in Projects.

### Safer media handling
- Detailed FFprobe preflight detects missing video/audio streams and unusual media.
- Odd containers/codecs/frame rates/rotation can be normalized to a stable H.264/AAC working copy before analysis.
- Free-disk checks run before heavy processing.
- Temporary/chunk files are cleaned without deleting project outputs.
- Existing transcript and render caches are retained.

### Processing profiles
Choose one per project:
- **Low memory** — 3-minute transcription chunks and fewer CPU threads for constrained machines.
- **Balanced** — 5-minute chunks; recommended default.
- **Fast** — 10-minute chunks/more CPU threads when the machine has headroom.

If NumPy/faster-whisper still reports an allocation error, M2.1 automatically re-splits only the failing chunk into smaller pieces and continues with the correct timeline offset.

The default remains lightweight English-only `tiny.en` on CPU.

### Editing without rerunning AI
After Clip AI finds a moment you can:
- nudge/edit the clip start and end time;
- load and correct the transcript text used for captions;
- select a different cover-frame position;
- re-render only what changed.

### Complete export package
Every rendered Short can be downloaded normally or exported as a ZIP containing:

```text
short.mp4
cover.jpg          (when available)
subtitles.srt
subtitles.vtt
metadata.json
```

Rendered MP4s also receive a generic `.metadata.json` sidecar containing the saved title/caption and clip metadata. It is intentionally app-agnostic so other local publishing tools can read it without Clip AI depending on them.

### Projects and support
- Search/filter Projects by title/status/source.
- Resume recoverable projects from the Projects page.
- Export a redacted diagnostic ZIP from System when troubleshooting.
- Task history is persisted locally.
- Versioned project schema/config migrations protect older projects.

### Easier local startup
Run `START_CLIP_AI.bat` from the project root. It checks the main local prerequisites, starts the worker and web app in separate windows, then opens Clip AI.

For a quick prerequisite check without starting the app, run `CHECK_CLIP_AI.bat`.

## Windows installation and startup

### Update an existing Windows installation

Close the worker and web Command Prompt windows first. Save the M3 ZIP as
`C:\Users\PC\Downloads\clip-ai-v22-m3-social-metadata.zip`, then open **Command Prompt** and run:

```bat
cd /d C:\Users\PC\Downloads
tar -xf "clip-ai-v22-m3-social-metadata.zip"
xcopy "C:\Users\PC\Downloads\clip-ai-starter-v22-m3\*" "C:\Users\PC\Downloads\clip-ai-starter" /E /I /Y
cd /d C:\Users\PC\Downloads\clip-ai-starter\apps\worker
.venv\Scripts\activate
pip install -r requirements.txt
cd /d C:\Users\PC\Downloads\clip-ai-starter\apps\web
npm install
npm run build
cd /d C:\Users\PC\Downloads\clip-ai-starter
START_CLIP_AI.bat
```

The ZIP contains source, tests and documentation only; copying it over the
installation retains your local `.env`, worker `.venv`, saved projects and media.
If `npm run build` fails on Windows, record the exact error before continuing; the update block intentionally stops there before startup.

### Manual worker startup
```bat
cd /d C:\Users\PC\Downloads\clip-ai-starter\apps\worker
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Manual web app startup
```bat
cd /d C:\Users\PC\Downloads\clip-ai-starter\apps\web
npm run dev
```

Open `http://localhost:3000`.

## Recommended local environment

```env
TRANSCRIPTION_BACKEND=local
RANKING_BACKEND=local
LOCAL_WHISPER_MODEL=tiny.en
LOCAL_WHISPER_DEVICE=cpu
LOCAL_WHISPER_COMPUTE_TYPE=int8
LOCAL_WHISPER_CPU_THREADS=4
PROCESSING_PROFILE=balanced
MIN_FREE_DISK_GB=2.0
```

`OPENAI_API_KEY` is optional for the local configuration and should never be committed.

## Tests

v22 M3 currently passes **68 backend tests**, including M3 grounding/tag tests plus the M2.1 memory-pressure, compilation-boundary, natural-ending, variable-duration, scene-diversity and v21 reliability suites. TSX syntax validation passes in this workspace. Full Next.js dependency/type/build validation should be run by `npm install` + `npm run build` on Windows as part of the normal update command.

## Current boundary

This remains a local beta. A future hosted Clip AI service should replace local project media/task persistence with authenticated user accounts, object storage, a database and durable cloud queues/workers. v21 deliberately focuses on making the local product stable rather than prematurely coupling it to that future cloud architecture.
