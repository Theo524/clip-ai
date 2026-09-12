# Clip AI v21 · Long-Term Beta

Clip AI turns long English-language videos into ranked, reframed, captioned, ready-to-post vertical Shorts. v21 is a reliability and editing release intended to be a stable local beta for an extended testing period.

## v21 highlights

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
- **Low memory** — smaller chunks and fewer CPU threads for constrained machines.
- **Balanced** — recommended default.
- **Fast** — larger chunks/more CPU threads when the machine has headroom.

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

## Manual startup

### Worker
```bat
cd /d C:\Users\PC\Downloads\clip-ai-starter\apps\worker
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Web app
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

v21 currently ships with **46 passing backend tests**, including persistence/migration, transcription recovery, processing profiles, subtitle exports, ranking/render behavior and reliability checks. Core frontend TSX files also pass a TypeScript transpilation/syntax check.

## Current boundary

This remains a local beta. A future hosted Clip AI service should replace local project media/task persistence with authenticated user accounts, object storage, a database and durable cloud queues/workers. v21 deliberately focuses on making the local product stable rather than prematurely coupling it to that future cloud architecture.
