# Clip AI — Milestone 2.1 (local development mode)

This build removes the API-credit blocker for development.

## What works

- Upload MP4/MOV/MKV/WEBM/M4V/AVI video files you own or are authorised to use
- FFmpeg extracts audio
- **faster-whisper runs locally on your PC** and produces timestamped transcript segments
- A **local heuristic ranker** returns real clip candidates without API credits
- YouTube URL demo mode remains available
- OpenAI transcription/ranking code remains available as an optional production upgrade

## Important first-run behaviour

The first real upload downloads the configured Whisper model (`small.en`) to your computer. This can take a little while and uses several hundred MB of disk space. Later runs reuse the cached model.

The default is CPU + int8, so you do not need CUDA or an NVIDIA GPU.

## Update an existing Milestone 2 checkout

Copy these files over your existing project and replace matching files. Then, in the worker virtual environment:

```bat
cd apps\worker
.venv\Scripts\activate
pip install -r requirements.txt
```

Open `.env` and use:

```env
MOCK_MODE=false
TRANSCRIPTION_BACKEND=local
RANKING_BACKEND=local
LOCAL_WHISPER_MODEL=small.en
LOCAL_WHISPER_DEVICE=cpu
LOCAL_WHISPER_COMPUTE_TYPE=int8
```

Your existing `OPENAI_API_KEY=...` can stay in `.env`; it will not be used while both backends are set to `local`.

Start the worker:

```bat
uvicorn main:app --reload --port 8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

You want `transcription_backend: "local"`, `ranking_backend: "local"`, and `ffmpeg_available: true`.

Start the web app in another terminal as before:

```bat
cd apps\web
npm install
npm run dev
```

Open `http://localhost:3000`, upload a 2–5 minute talking-head video, and click **Analyze real video**.

## Later: higher-quality ranking

Once API billing is enabled, change only:

```env
RANKING_BACKEND=openai
```

That keeps local transcription (cheap/free development) while using the hosted model for smarter clip selection.

## Next milestone

Take a selected timestamp and render a real 9:16 MP4 with captions.
