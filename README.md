# Clip AI v20 Beta Release Candidate

Clip AI turns long videos into ranked, reframed, captioned, ready-to-post vertical clips. v20 is the **local beta release candidate**: it freezes the core creative feature set and focuses on making the app understandable and safe for another person to run on a development PC.

## v20 highlights

- **First-run onboarding**: a short welcome flow explains the simplest path — add a video, choose a Best 3 moment, press Create Short.
- **System preflight**: the new `/status` page checks FFmpeg, FFprobe, transcription, ranking, smart reframing, workspace write access and free disk space.
- **Local privacy summary**: the status page makes it clear whether transcription/ranking are local or using an external API.
- **Storage visibility**: shows project count, project storage use and free disk space.
- **Safe cleanup tool**: removes stale `.part` renders and disposable completed-project audio without deleting source videos, transcripts, finished Shorts or projects.
- **Beta/version identity**: the UI and worker now report `20.0.0-beta.1` / Beta Release Candidate.
- **v19.1 stabilized virtual camera retained**: small face movements no longer cause constant micro-pans.
- All existing features remain: Upload + YouTube project tabs, Best 3 scoring, batch rendering, active-speaker framing, adaptive layouts, word-timed caption presets, smart titles/post copy, projects/history, covers and ready-to-post export.

## Run locally

Backend:

```bat
cd C:\Users\PC\Downloads\clip-ai-starter\apps\worker
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bat
cd C:\Users\PC\Downloads\clip-ai-starter\apps\web
npm run dev
```

Open:

```text
http://localhost:3000
```

System check:

```text
http://localhost:3000/status
```

## Recommended local config for the current 8 GB development PC

```env
MOCK_MODE=false
TRANSCRIPTION_BACKEND=local
RANKING_BACKEND=local
LOCAL_WHISPER_MODEL=tiny.en
LOCAL_WHISPER_DEVICE=cpu
LOCAL_WHISPER_COMPUTE_TYPE=int8
CLEANUP_TEMP_AUDIO=true
```

`base.en` can improve transcription quality, but `tiny.en` remains the safer low-memory default.

## What “beta release candidate” means

v20 is a complete **local product beta**, not yet a hosted SaaS launch. It intentionally does **not** add cloud accounts, hosted video workers, shared team projects or payments. Those require deployment infrastructure and should be added after this local build has been used on a broader set of real videos.

The core loop is now frozen for beta testing:

```text
Add video
→ transcribe
→ rank moments
→ choose Best 3 / more suggestions
→ Auto or custom framing + captions
→ render
→ title + post caption + cover
→ download / reopen from Projects
```

## Beta smoke test

See `BETA_CHECKLIST.md` before tagging a release or sharing the app with another tester.
