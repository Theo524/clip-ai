# Clip AI — Milestone 7

Local-first prototype for turning long videos into short-form clips.

## What changed in Milestone 7

The renderer now treats the **9:16 canvas** and the **actual video picture** as two different things.

- **Fill** — full 9:16 subject-aware crop for talking heads.
- **Focus** — large central portrait-friendly crop on a plain dark canvas; ideal for movies/dialogue/scenic footage.
- **Backdrop** — the same central crop with a subdued blurred background.
- **Preserve** — keeps already-vertical footage intact.
- Removed the old full-16:9-inside-9:16 Cinema/fit approach.
- Focus/Backdrop have Compact, Balanced and Immersive frame-size presets.
- Captions are always rendered **inside the actual video picture**, never in the empty/blurred margins.
- Multi-face samples use group-aware horizontal framing.

## Recommended movie setup

```text
Framing: Focus
Frame size: Balanced
Captions: Cinematic
```

Balanced creates a 720×900 (4:5) video window centered within the 720×1280 Short. The surrounding area is plain dark and intentionally quiet. Cinematic captions sit on the lower portion of the picture itself.

## Run the worker

```bat
cd apps\worker
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Run the web app

```bat
cd apps\web
npm run dev
```

Open `http://localhost:3000`.

Your real `.env` remains gitignored and should never be committed.
