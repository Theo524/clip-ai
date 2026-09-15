# Clip AI v23 M5 handoff

## Product boundary
Clip AI remains the public/local-first clip-making app. Clip Relay remains private and separate. Do not add Relay-specific publishing controls to Clip AI.

## M5 quality rules
- Local transcription stays English-only.
- Explicit Show/program/subject text is trusted context; filenames are not.
- Hotwords are optional/compatibility-safe and must never make old faster-whisper installs fail.
- Captions remain quote-faithful. M5 may improve line breaks but must not rewrite spoken dialogue.
- Titles/descriptions/tags must stay grounded in clip/context/subject hint and must not invent people or character names.
- Ranking should prefer complete setup → payoff → reaction and penalize boundaries requiring manual repair.

## Anime visual contract
Do not change without an explicit user request:
- black 9:16 canvas;
- Focus + Compact central picture;
- Cinematic captions;
- captions low inside the anime picture, not in the black bars;
- calm scene-aware tracking.

## Reliability inherited from M4.4
- Long-source smaller speech chunks under memory pressure.
- base.en → tiny.en memory fallback where required.
- release cached Whisper/CTranslate2 model before render.
- x264 allocator failure retry with ultrafast single-thread encoder.
- final render remains 720x1280.

## Validation
- Backend tests: 135 passed, 0 failed.
- Python compile: clean.
