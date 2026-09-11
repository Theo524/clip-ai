# Clip AI — Milestone 3

A local-first prototype for turning long-form video into ranked short-form candidates and rendering chosen moments into real MP4 clips.

## What works now

- Upload an authorised local video.
- FFmpeg extracts audio.
- Local `faster-whisper` produces timestamped transcript segments.
- A zero-cost local development ranker proposes candidate moments.
- Each real candidate has a **Generate MP4** button.
- FFmpeg makes a frame-accurate H.264/AAC MP4 from the original source.
- The generated clip plays in the browser and can be downloaded.
- YouTube URL mode remains a demo; direct arbitrary YouTube downloading is intentionally not wired in.

## Run the worker

```bat
cd apps\worker
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Health check:

`http://127.0.0.1:8000/health`

For an 8 GB Windows development machine, these `.env` values are a good starting point:

```env
MOCK_MODE=false
TRANSCRIPTION_BACKEND=local
RANKING_BACKEND=local
LOCAL_WHISPER_MODEL=tiny.en
LOCAL_WHISPER_DEVICE=cpu
LOCAL_WHISPER_COMPUTE_TYPE=int8
```

## Run the web app

```bat
cd apps\web
npm install
copy .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`.

## Local files

Real uploads and generated clips are stored under `apps/worker/work/<job-id>/` while you develop. The `work/` directory is ignored by Git.

## Next milestone

Take a generated cut and create a true short-form composition:

1. 9:16 vertical canvas
2. smart crop/reframe
3. burned/animated captions
4. optional title/hook layer
5. speaker/face tracking
