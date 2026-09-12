# Clip AI v20.1 · Clip Relay Visual Refresh

This package keeps the **v20.1 processing pipeline unchanged** and ports the visual language of Clip Relay onto the Clip AI web app. It is intentionally a design-only refresh so transcription, ranking, rendering, projects and system checks keep the same behaviour.

## Visual refresh

- Clip Relay-inspired dark glass surfaces and softer depth
- Violet-to-cyan ambient gradients and matching brand mark
- More compact navigation, status chips and controls
- Refined upload surface, project cards, Best 3 results and system screen
- Unified buttons, borders, hover states and scrollbars
- Responsive mobile treatment without changing the workflow

---

## Original v20.1 Beta Reliability Patch

Clip AI turns long English-language videos into ranked, reframed, captioned, ready-to-post vertical clips. v20.1 is a beta reliability/UX patch on top of the v20 local release candidate.

## What changed in v20.1

### More reliable transcription
- Keeps the lightweight English-only `tiny.en` default.
- Checks that a source video actually contains an audio stream before transcription.
- Local Whisper first uses VAD (speech/silence filtering) for speed.
- If a chunk returns no transcript, Clip AI automatically retries that chunk **without VAD**. This is useful for quiet film dialogue, music-heavy mixes, or speech VAD mistakenly rejects.
- If both passes fail, the error now explains that no audible English speech was found instead of only saying “No transcript segments were produced.”

### Faster repeated work + better long-video feedback
- Adds a local transcript cache keyed from the video content + transcription model/settings. Re-uploading the same source can reuse the transcript instead of running Whisper again.
- Existing project transcripts are also reused.
- Videos of 30 minutes or more are processed in up-to-10-minute audio chunks for more useful progress/cancel checkpoints.
- Progress messages include chunk counts and an ETA estimate after the first chunk finishes.
- Local Whisper is explicitly tuned to 4 CPU threads by default. Override with `LOCAL_WHISPER_CPU_THREADS` if needed.

> `tiny.en` is already the fastest practical local model in this build. The cache and CPU/progress changes remove wasted work, but a brand-new one-hour video will still take meaningful time on an 8 GB laptop. Cloud transcription is the eventual speed path for production.

### Cleaner home/results experience
- Homepage headline is now simply **“Turn long videos into ready-to-post Shorts.”**
- The duplicate System/readiness block was removed from the middle of the home screen. **System remains in the navbar.**
- Results now put the **Best 3** first with only the information needed to decide: title, score, short “Starts with” preview, Create Short, and an optional “Why this clip?” disclosure.
- Detailed clip controls, the video-settings guide, saved renders, transcripts/copy controls, and the remaining editing UI are grouped under **More suggestions & editing options**.
- A rendered Best 3 Short can be previewed/downloaded directly from its compact card.

## Run locally

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

## Recommended local transcription settings

```env
TRANSCRIPTION_BACKEND=local
LOCAL_WHISPER_MODEL=tiny.en
LOCAL_WHISPER_DEVICE=cpu
LOCAL_WHISPER_COMPUTE_TYPE=int8
LOCAL_WHISPER_CPU_THREADS=4
```

The project remains English-first by design.

## Tests

v20.1 ships with **41 passing backend tests**. The current frontend TSX files also pass a TypeScript syntax/transpilation check.
