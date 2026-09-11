# Clip AI — Milestone 12

Clip AI turns long-form video into short-form clips with local transcription, local moment ranking, adaptive layouts, smart captions, and FFmpeg rendering.

## New in Milestone 12

The **YouTube link** tab is now a real project flow instead of a mock demo.

1. Paste a YouTube URL.
2. Clip AI reads the public title/channel/thumbnail through YouTube oEmbed.
3. Confirm that you own the video or have permission to process it.
4. Choose the matching source video file from your computer.
5. The video runs through the same real local Whisper + ranking + render pipeline as a normal upload, while preserving the YouTube URL as the project source.

This version intentionally does **not** depend on an unofficial arbitrary YouTube downloader. The official YouTube APIs do not provide a general endpoint for downloading the source bytes of public videos, so the development build keeps ingestion reliable and rights-aware by pairing the link with an authorised local source file.

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
- Smart 9:16 reframing with Fill / Focus / Backdrop / Preserve
- Viral, Cinematic, Clean, and Meme caption presets
- Stable word highlighting and caption-safe placement
- YouTube project metadata + authorised source-file analysis
- FFmpeg short rendering and original clip export
