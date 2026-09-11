# Clip AI — Milestone 14

Clip AI turns long-form video into short-form clips with local transcription, local moment ranking, adaptive layouts, smart captions, persistent projects, and now dialogue-based clip titles/social copy.

## New in Milestone 14

Each suggested moment now gets useful copy generated from the exact dialogue inside that selected clip.

- The clip title is no longer just a chopped transcript opening.
- Open **Title & post caption** on any clip to edit the generated title.
- A short social post caption is generated from the same dialogue.
- Regenerate copy as **Auto**, **Viral**, **Clean**, or **Cinematic**.
- Manual edits can be saved back into the local project.
- Reopened projects keep the saved title and social caption.

The local copywriter deliberately stays grounded in the spoken dialogue; it shortens and reframes wording but does not invent claims that were not in the source.

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
- FFmpeg short rendering and original clip export
