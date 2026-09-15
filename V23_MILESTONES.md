# Clip AI v23 milestone map

- **M1 — Narrative Intelligence 2.0: complete.** Necessary setup, question/answer flow, setup/payoff continuation, narrative completeness scoring, dynamic-but-not-forced duration, and hard scene boundaries.
- **M1.1 — Simpler context UI: complete.** Public Clip length and Audio track selectors removed; both behaviors stay automatic. Content type + Video structure remain the main context controls.
- **M2 — Boundary Refinement: complete.** Immediate reactions, same-thought continuation, compact setup rescue, boundary-confidence scoring, and shortest-complete-window preference.
- **M3 — Quality Pass / Stable Candidate: complete.** Stronger short-fragment protection for story-heavy media, composite selection quality, full-text duplicate suppression, stronger Best 3 diversity, pinned frontend dependencies, and regression hardening.

## Frozen behavior

- Anime Auto: black canvas + Compact central frame + Cinematic captions locked low inside the picture.
- Memory-safe local Whisper retry and transcript caching.
- Grounded title/description/hashtags with scene-local context.
- Quick previews, replacement feedback, caption timing nudges and manual trim/caption correction.
- Source/cache cleanup and recovery.
- Public Clip AI remains independent from private Clip Relay.
- Create UI remains intentionally small: Content type, Video structure, optional subject hint, processing profile.

## Next

Real-world test M3. If no ranking/framing regressions appear, call v23 stable and stop adding features for a while.
