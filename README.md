# Clip AI — Milestone 2

This build adds **real local video analysis**.

## What works

- YouTube URL demo mode (same as Milestone 1)
- Upload an MP4/MOV/MKV/WEBM/M4V/AVI file
- FFmpeg extracts audio into podcast-friendly chunks
- OpenAI timestamped transcription
- AI ranks the best 20–60 second moments
- Real timestamps, titles, hooks, scores and reasons appear in the web UI

The upload flow is intended for video you own or are authorised to use.

## Windows setup

### A. Check FFmpeg

Open Command Prompt and run:

```bat
ffmpeg -version
```

If Windows says it cannot find `ffmpeg`, install FFmpeg first and ensure the command works before continuing.

### B. Worker

```bat
cd apps\worker
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Open `apps\worker\.env` and change:

```env
MOCK_MODE=false
OPENAI_API_KEY=your_key_here
```

Do not share your API key in chat or commit it to Git.

Then start the worker:

```bat
uvicorn main:app --reload --port 8000
```

Optional health check in a browser:

```text
http://127.0.0.1:8000/health
```

You want `api_key_configured: true` and `ffmpeg_available: true`.

### C. Web app

In another Command Prompt:

```bat
cd apps\web
npm install
copy .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`, choose **Upload video · real**, select a short test video, and click **Analyze real video**.

Start with a 5–15 minute talking-head video while testing. Long-video chunking is already included, but short files make debugging much faster.

## Next milestone

Take one returned timestamp and automatically:

1. cut the original video,
2. smart-crop it to 9:16,
3. generate word-level captions,
4. render a playable MP4.
