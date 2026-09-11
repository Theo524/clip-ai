# Clip AI — Milestone 15

Clip AI turns long-form video into short-form clips with local transcription, local moment ranking, adaptive layouts, smart captions, persistent projects, dialogue-based copy, and now a ready-to-post export handoff.

## New in Milestone 15

A finished vertical Short now opens a single **Ready to post** panel instead of leaving the user to collect pieces from different controls.

- Play the rendered Short.
- See a simple title/thumbnail-style preview.
- Copy the generated title with one click.
- Copy the social caption with one click.
- Copy title + caption together.
- Download with a human-readable filename derived from the editable clip title.
- Keep technical render details collapsed unless they are needed.

The internal render cache still uses stable technical filenames; only the browser download name is polished. That means changing a title does not force the video to re-render.

## Run

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

## Current pipeline

- Local faster-whisper transcription with word timestamps
- Local clip ranking with cleaner moment boundaries
- Dialogue-based title + social caption generation
- Smart 9:16 reframing with Fill / Focus / Backdrop / Preserve
- Viral, Cinematic, Clean, and Meme caption presets
- Stable word highlighting and caption-safe placement
- Personal upload + YouTube project workflows
- Persistent local Projects/history screen
- Ready-to-post export panel with polished download naming
- FFmpeg short rendering and original clip export
