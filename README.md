# Clip AI v23 · Stable Candidate (M3)

Clip AI turns long English-language videos into ranked, reframed, captioned vertical Shorts. v23 focuses on one thing: **better complete moments without turning the interface into a settings dashboard**.

## v23 quality improvements

- Necessary setup and question/answer protection.
- Setup/payoff continuation and immediate-reaction protection.
- Dynamic duration: longer only when the scene actually needs it.
- Stronger protection against story-heavy clips that are catchy but too short to make sense.
- Best 3 diversity across scenes, moment types and full-text topic overlap.
- Narrative + boundary quality influence selection so clips needing less repair win close comparisons.
- Grounded titles, descriptions and tags remain scene-local.
- Frontend versions are pinned to the validated Next.js/React stack for repeatable installs.

## Intentionally simple UI

The public create form stays focused on **Content type**, **Video structure**, optional **Show / program / subject**, and the processing profile. Clip length and audio selection remain automatic.

Anime Auto remains unchanged: **black vertical canvas + Compact central picture + Cinematic captions locked low inside the picture + calmer tracking**.

## Windows update

Keep your existing project at:

`C:\Users\PC\Downloads\clip-ai-starter`

Put the update ZIP in Downloads and run the included updater from Command Prompt. It preserves `.git`, `.venv`, projects, renders and local settings; replaces application code, runs backend tests, installs the pinned frontend stack, builds from a clean Next cache, and starts Clip AI.

## Validation

- Backend: **112 tests passed**
- Python compile: clean
- Windows updater performs the full Next.js production build before startup.
