# Clip AI — Milestone 9

Local-first prototype for turning long videos into short-form clips.

## What changed in Milestone 9

This milestone fixes the Viral Pop / Meme caption flicker and adds lightweight **caption-safe placement**.

- **Stable phrase layer:** Viral Pop and Meme keep the full phrase continuously visible for the phrase lifetime.
- **Active-word overlay:** only the currently spoken word is drawn again in the accent colour.
- **No whole-caption re-entry between words:** word changes no longer restart the phrase fade/animation.
- **Small active-word jump:** the accent word rises a few pixels into place without moving the base phrase or changing its width.
- **Phrase transitions still exist:** the whole phrase can fade in/out only when the phrase itself changes.
- **Caption-safe zones:** the existing face-sampling pass now records whether important faces tend to occupy the upper, middle, or lower part of the picture.
- Auto placement chooses an in-picture **upper / middle / lower** caption band that better avoids the dominant face region.
- **Cinematic** still naturally prefers the lower part of the actual video picture; **Viral Pop / Meme** naturally prefer the middle unless that area is face-heavy.
- Captions remain inside the actual video window for Fill, Focus, Backdrop and Preserve.
- Milestone 8 word-level Whisper timing and the Caption sync slider remain intact.

## What the stable Viral Pop rendering does

```text
PHRASE LIFETIME
"this really works now"  ← one stable base event

WORD 1
THIS really works now     ← active overlay only

WORD 2
this REALLY works now     ← base phrase never disappears

WORD 3
this really WORKS now
```

The active overlay uses transparent placeholders for the other words, so the highlighted word stays aligned with the stable phrase. Its tiny upward movement gives a pop effect without horizontal jitter.

## Caption placement

The smart reframe pass now records coarse face occupancy:

```text
upper / middle / lower
```

Auto caption placement reuses that data instead of running another heavy detector. If there is no reliable face evidence, presets keep their natural position:

- Cinematic / Clean → lower
- Viral Pop / Meme → middle

## Important after upgrading

Milestone 9 uses new cache names for the reframe plan and rendered Short. That means an already-analysed job can be rendered again and still receive the new stable-caption behaviour.

For the best word timing, jobs should still come from a Milestone 8+ analysis with word timestamps.

## Recommended movie setup

```text
Framing: Focus
Frame size: Balanced
Captions: Cinematic
Caption sync: 0 ms
```

## Recommended podcast / talking-head setup

```text
Framing: Auto or Fill
Frame size: Balanced
Captions: Viral Pop
Caption sync: 0 ms
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
