# Clip AI v23 milestone map

- **M1 — Narrative Intelligence 2.0: complete.** Necessary setup, question/answer flow, setup/payoff continuation, narrative completeness scoring, dynamic-but-not-forced duration, and hard scene boundaries.
- **M1.1 — Simpler context UI: complete.** Public Clip length and Audio track selectors removed. Content type + Video structure remain the main context controls.
- **M2 — Boundary Refinement: complete.** Immediate reactions, same-thought continuation, compact setup rescue, boundary-confidence scoring, and shortest-complete-window preference.
- **M3 — Quality Pass: complete.** Stronger short-fragment protection, better Best 3 diversity, pinned frontend dependencies, and regression hardening.
- **M4 — Speech & Copy Quality: complete.** Stronger English transcription/rescue, timing-preserving caption corrections, less generic titles/descriptions/tags.
- **M4.1–M4.3 — Reliability hotfixes: complete.** Windows test compatibility, long-video memory recovery, Whisper cache release before render, low-memory x264 retry.
- **M4.4 — English-only speech rollback: complete.** Removed experimental multilingual detection/translation after real-world testing.
- **M5 — Final Quality Pass: current.** Trusted speech hotwords, natural caption line breaks, stronger metadata clause selection, and setup/payoff/reaction repair-cost ranking.

## Frozen behavior
- Anime Auto: black canvas + Compact central frame + Cinematic captions locked low inside the picture.
- English-only local Whisper with transcript caching and confidence rescue.
- Grounded title/description/hashtags with scene-local context and no invented names.
- Quick previews, replacement feedback, caption timing nudges and manual trim/caption correction.
- Source/cache cleanup and recovery.
- Public Clip AI remains independent from private Clip Relay.
- Create UI remains intentionally small: Content type, Video structure, optional subject hint, processing profile.
