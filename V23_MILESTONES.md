# Clip AI v23 milestone map

- **M1 — Narrative Intelligence 2.0: complete.** Necessary setup, question/answer flow, setup/payoff continuation, narrative completeness scoring, dynamic-but-not-forced duration, and hard scene boundaries.
- **M1.1 — Simpler context UI: complete.** Public Clip length and Audio track selectors removed; both behaviors stay automatic. Content type + Video structure remain the main context controls.
- **M2 — Boundary Refinement: complete.** Immediate reactions, same-thought continuation, compact setup rescue, boundary-confidence scoring, and shortest-complete-window preference. No new public controls.

## v22 behavior that remains frozen

- Anime Auto: black canvas + Compact central frame + Cinematic captions locked low inside the picture.
- Memory-safe local Whisper retry and transcript caching.
- Grounded title/description/hashtags with scene-local context.
- Best 3 diversity, quick previews, replacement feedback, caption timing nudges.
- Dual-audio handling and source/cache cleanup remain automatic/private where applicable.
- Public Clip AI remains independent from private Clip Relay.

## Next v23 work

Run real-source regression tests on anime, documentary and comedy. Prefer bug fixes and ranking calibration over adding UI. If boundary quality is stable, the next separate product milestone is Clip Relay v1.5 Trend Scout.
