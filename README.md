# Clip AI — Milestone 1

A starter implementation for an AI long-form-to-shorts product.

Current vertical slice:

1. Paste a YouTube URL in the web UI.
2. The web app sends it to the processing worker.
3. The worker returns ranked short-form clip suggestions with timestamps, titles, hooks and scores.
4. `MOCK_MODE=true` works immediately without API keys or media ingestion.
5. Real mode can analyze a local/authorized media file: FFmpeg extracts audio, OpenAI transcribes it, and an OpenAI model ranks clip-worthy moments.

> The repo intentionally does **not** include an unofficial YouTube downloader. For production, connect an authorised/owned-media import path (YouTube-authorised access, creator upload, cloud storage import, etc.) to the `MediaImporter` boundary.

## Architecture

```text
Next.js web UI
    |
    | POST /api/analyze
    v
FastAPI worker
    |
    +-- media import boundary (mock for now)
    +-- FFmpeg audio extraction
    +-- speech-to-text with timestamps
    +-- AI clip ranking
    +-- later: crop/face tracking/captions/rendering
```

## Run locally

### 1) Worker

```bash
cd apps/worker
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

The default `.env.example` uses `MOCK_MODE=true`, so it runs without an OpenAI key.

### 2) Web app

```bash
cd apps/web
npm install
cp .env.local.example .env.local
npm run dev
```

Open http://localhost:3000.

## Real analysis of an authorised local video

Set in `apps/worker/.env`:

```env
MOCK_MODE=false
OPENAI_API_KEY=...
```

Then POST directly to the worker with a file that exists on the worker machine:

```bash
curl -X POST http://localhost:8000/analyze \
  -H 'content-type: application/json' \
  -d '{
    "source_url":"https://www.youtube.com/watch?v=example",
    "local_media_path":"/absolute/path/to/video.mp4",
    "max_clips":5
  }'
```

This is the seam where the authorised YouTube/media importer will plug in next.

## Next milestone

- Authorised media import / creator upload
- Background jobs + progress states
- Automatic MP4 cutting with FFmpeg
- 9:16 smart crop / face tracking
- Word-level animated captions
- Download/export screen
