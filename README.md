# Clip AI v22 M2.1 · Smarter Clip Intelligence + Memory Safety

Clip AI turns long English-language videos into ranked, reframed, captioned, ready-to-post vertical Shorts. v22 is being delivered in guarded milestones. M2.1 keeps M2 clip intelligence and patches local Whisper memory pressure seen on 8 GB Windows PCs. The v21 render and recovery pipeline remains in place.

## v22 M2 highlights

- Transcript pauses, local topic shifts and compilation cues divide the source into independent scenes. For anime, film and compilations, a bounded FFmpeg keyframe scan supplies optional shot cues; if it fails or times out, transcript segmentation still works. Dialogue cuts alone do not split a scene.
- Candidates use genre-specific **soft** duration ranges, then extend to a sentence, answer, joke or payoff where possible. A cut after “but”, “because” or “and then” is rejected. An uncertain boundary is flagged.
- Ranking weighs standalone context, story completeness, hook, payoff, speech quality and transcript confidence. When shot sampling succeeds, frequent cuts also reduce visual suitability slightly and flag the framing for review. Best 3 favor different strong scenes. Remaining distinct candidates support **Replace suggestion**, with no new transcription or analysis. Restore top picks returns to the original selection; replacements on the results page are session-only.
- Each new candidate records its scene bounds, moment type and quality warnings. A local context window cannot reach across a detected scene boundary. The subject field remains a hint, never a claim about an unrelated compilation scene.
- Existing saved M1 projects and edits keep their recommendations when reopened or resumed. To compare the M2 selector on that source, create a new analysis; cached transcription may be reused.
- OpenAI ranking remains its existing path; M2 scoring and scene-local selection apply to the default **local** ranking backend. Visual framing/caption intelligence and social copy generation remain for later milestones.

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

### Update an existing Windows M1 installation

Close the worker and web Command Prompt windows first. Save the M2 ZIP as
`C:\Users\PC\Downloads\clip-ai-v22-m2-smarter-clips.zip`, then open **Command Prompt** and run:

```bat
cd /d C:\Users\PC\Downloads
tar -xf "clip-ai-v22-m2-smarter-clips.zip"
xcopy "C:\Users\PC\Downloads\clip-ai-starter-v22-m2\*" "C:\Users\PC\Downloads\clip-ai-starter" /E /I /Y
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
If `npm run build` fails on Windows, record the exact error before testing M2.

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

v22 M2.1 ships with the M2 suite plus memory-pressure regression tests, including compilation boundaries, natural endings, variable duration, scene diversity and quality warnings along with the M1/v21 regression tests. Frontend TypeScript checking (`tsc --noEmit`) passes. This workspace could not complete Next's production build because its process runner returned `ENOENT: uv_resident_set_memory`; run `npm run build` on Windows before considering M2 fully validated.

## Current boundary

This remains a local beta. A future hosted Clip AI service should replace local project media/task persistence with authenticated user accounts, object storage, a database and durable cloud queues/workers. v21 deliberately focuses on making the local product stable rather than prematurely coupling it to that future cloud architecture.
