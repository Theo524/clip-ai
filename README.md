# Clip AI v23 · Narrative Intelligence 2.0 (M1)

Clip AI turns long English-language videos into ranked, reframed, captioned vertical Shorts. v23 M1 keeps the stable v22 rendering/transcription pipeline and changes one core thing: **clip boundaries now care more about whether the story actually makes sense**.

## What changed in v23 M1

- **Necessary setup detection** — reply-like or pronoun-only openings lose points unless the needed setup is included.
- **Question → answer protection** — a clip will not stop on a question when the answer follows immediately.
- **Setup → payoff protection** — late pivots, reasons and consequences extend when the next line completes the thought.
- **Dynamic duration** — anime, film, podcast and documentary clips can exceed their normal guide when the narrative genuinely needs it.
- **No forced stretching** — complete punchlines and short self-contained moments stay short.
- **Scene-safe context** — narrative extension never crosses a detected compilation/topic boundary.
- **Narrative score** — the existing “Why this clip?” breakdown now includes a Narrative metric.

Everything from the frozen v22 build remains: memory-safe Whisper, grounded titles/descriptions/tags, Anime Auto black canvas + Compact frame + low Cinematic captions, previews, replacement suggestions, dual-audio handling, source cleanup and recovery.

## Windows update

Keep your existing project at:

`C:\Users\PC\Downloads\clip-ai-starter`

Put the v23 ZIP in Downloads and run the included updater from Command Prompt. The updater preserves `.git`, `.venv`, projects, renders and local settings; it replaces application code, runs backend tests, builds the frontend from a clean Next cache, then starts Clip AI.

## Validation

- Backend: **98 tests passed**
- Python compile: clean
- Frontend change is copy-only; the Windows updater runs the full Next.js production build before startup.
