# Clip AI v23 M5 · Final Quality Pass

Clip AI turns long videos into ranked, reframed, captioned vertical Shorts. M5 is the final desktop quality pass: no new public controls, no multilingual comeback, and no change to the established Anime Auto visual contract.

## M5 focus

### Stronger English speech accuracy

- Local transcription remains **English-only**.
- **Balanced** continues to use `base.en`; Fast/Low-memory keep their lighter first pass plus confidence rescue.
- The optional Show / program / subject hint is now also supplied as trusted Whisper **hotword vocabulary** when the installed faster-whisper build supports it. This is conservative: Clip AI never promotes filenames or outside guesses into speech vocabulary.
- Balanced uses a slightly stronger beam while keeping the existing low-memory retry path.
- Questionable chunks still get a focused stronger second pass, and the better transcript wins.
- M5 changes the transcript strategy version, so an old M4.4 transcript is refreshed once on re-analysis instead of silently hiding the accuracy changes.

### More natural captions

- Spoken wording remains quote-faithful to the timed transcript.
- Clean/Cinematic captions now choose intentional, balanced two-line breaks for dense phrases instead of relying entirely on libass auto-wrap.
- Line breaking avoids leaving articles/connectors stranded at the end of a row.
- Anime captions stay low **inside the actual Compact picture window**, exactly as before.

### Better titles, descriptions and tags

- Long dialogue is reduced to a meaningful complete clause before title length limits are applied, rather than blindly chopping a sentence.
- Descriptions prefer punctuation/clause boundaries and avoid endings such as `...and we.` caused by word-count truncation.
- User-supplied subject/show casing is restored consistently when that exact trusted term is already present.
- Generic conversational verbs are filtered more aggressively from free-form hashtags.
- No character/person names are invented.

### Stronger setup → payoff → reaction boundaries

- Immediate strong reactions are treated as part of the moment even when the preceding line already sounded like a grammatical conclusion.
- Candidates now record an internal `boundary_repair_cost` that penalizes clips needing context/ending repair.
- Best 3 still favors complete, diverse moments rather than three variants of the same scene.

## Frozen behavior

The public Create form remains intentionally small:

- Content type
- Video structure
- optional Show / program / subject
- Processing profile

There is still **no Clip length selector**, **no Audio track selector**, and **no language selector**.

Anime Auto remains:

- black 9:16 canvas;
- **Focus + Compact** central picture;
- Cinematic captions;
- captions low inside the picture, never the black bars;
- calm scene-aware tracking.

## Validation

- Backend regression suite: **135 passed, 0 failed** in the M5 source workspace.
- Python compile: clean.
- The Windows updater runs the backend suite again and rebuilds the Next.js frontend using the existing memory-safe build settings.
