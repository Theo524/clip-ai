# Clip AI — Milestone 10

Local-first prototype for turning long videos into short-form clips.

## What changed in Milestone 10

This milestone improves **which moments get selected**, rather than adding another visual effect.

The local zero-credit selector now prioritises:

- **Clean openings** — strongly penalises clips that begin as context-dependent fragments such as “and…”, “but…”, or “because…” unless the line is clearly an intentional hook.
- **Hooks** — rewards question-led openings, strong hook language, specific numbers and direct claims.
- **Complete ideas** — looks for a turn/pivot and a payoff or takeaway, not merely exciting vocabulary.
- **Tighter endings** — rewards clips that end on the conclusion and penalises extra chatter after the payoff.
- **Natural boundaries** — pauses and complete sentence endings help the candidate score.
- **Better Shorts length** — roughly 24–48 seconds is preferred when the idea is complete; 18–60 seconds remains valid.
- **Standalone context** — clips should make sense to someone who has not watched the surrounding video.
- **Duplicate suppression** — heavily overlapping and near-identical moments are filtered more aggressively.
- **Tiny edit padding** — selected timestamps include a small pre/post-roll so generated MP4s are less likely to cut the first or last phoneme.

The OpenAI ranking prompt has also been updated with the same editing rules for when `RANKING_BACKEND=openai` is enabled later.

## What did not change

Milestone 9's visual system remains intact:

- Fill / Focus / Backdrop / Preserve framing
- Compact / Balanced / Immersive video-window sizing
- word-level Whisper caption timing
- stable Viral Pop / Meme active-word highlights
- Cinematic / Clean caption presets
- caption-safe in-picture placement
- smart face/group/motion reframing

## Important after upgrading

**Re-analyse the video** to use the Milestone 10 selector. Existing analysed jobs already have their old clip suggestions saved, so simply re-rendering an old suggestion will not change its start/end timestamps.

A good comparison test is to analyse the same 5–10 minute talking video in Milestone 9 and Milestone 10 and look for:

```text
Milestone 9 candidate:
“And before that... [context] ... actual interesting point ... and then...”

Milestone 10 candidate:
“The biggest mistake I made was...”
        ↓
complete idea / turn
        ↓
“That’s why I now...”
        ↓
CUT
```

## Recommended development setup

Your current local configuration can remain:

```env
MOCK_MODE=false
TRANSCRIPTION_BACKEND=local
RANKING_BACKEND=local
LOCAL_WHISPER_MODEL=tiny.en
LOCAL_WHISPER_DEVICE=cpu
LOCAL_WHISPER_COMPUTE_TYPE=int8
```

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

Your real `.env`, generated media, virtual environment, Next.js build output and `node_modules` remain gitignored.
