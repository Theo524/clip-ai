# Clip AI v17

Local-first AI short-form video clipping prototype.

## What v17 changes

v17 is an intelligence/UX release rather than another single-feature patch:

- Adds an **AI Editor Picks / Best 3** section after analysis.
- Breaks each local score into **Hook, Standalone, Payoff, Retention and Clarity** so the ranking is understandable.
- Adds a short editor note explaining each candidate's strongest qualities and main trade-off.
- Adds **Render all 3**. Best picks render sequentially so an 8 GB development PC is not asked to encode three Shorts at once.
- Makes Auto framing more scene-aware by noticing multi-person shots and sampled scene cuts.
- Adds **Auto video size**: group/cut-heavy Focus clips preserve more context automatically.
- Keeps full vertical Fill for stable talking heads, Focus for cinematic/group scenes, Backdrop for motion/gameplay and Preserve for portrait footage.
- Improves dialogue-derived titles/social captions and reduces title/caption repetition.
- Keeps all v16 caption quality, platform presets, projects/history, cover frames and ready-to-post export features.

## Run locally

Backend:

```bat
cd apps\worker
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bat
cd apps\web
npm run dev
```

Open `http://localhost:3000`.

## Best 3 and batch rendering

After analysis, Clip AI ranks the candidates and shows the top three first. **Render all 3** renders those Shorts one at a time using each clip's Auto settings. Sequential rendering is deliberate for local development on modest hardware.

The full editable cards remain underneath, so titles, post captions, framing, caption style, platform safe-zones and timing can still be overridden per clip.

## Caption/transcription quality on an 8 GB PC

The safest default remains:

```env
LOCAL_WHISPER_MODEL=tiny.en
```

If you have enough free RAM, you can test:

```env
LOCAL_WHISPER_MODEL=base.en
```

`base.en` should improve transcription accuracy, but switch back to `tiny.en` if Windows reports memory-allocation errors.

## Notes

- Local Shorts render at 720×1280.
- Auto is still a recommendation system, not a hard rule; every important rendering choice can be overridden.
- YouTube projects use the authorised-source-file workflow rather than depending on an unofficial downloader.
