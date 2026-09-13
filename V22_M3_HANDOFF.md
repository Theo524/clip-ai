# Clip AI v22 M3 checkpoint / handoff

## Current stable development baseline

- Version: `22.0.0-m3`
- Release: **Titles & Social Metadata**
- Folder name in the update ZIP: `clip-ai-starter-v22-m3`
- Public Clip AI remains standalone. Clip Relay is separate/private and is not required by Clip AI.
- M2.1 memory-safe Whisper fallback is retained.

## Completed v22 milestones

- **M1 Context Foundation:** content type, structure, optional show/program/subject hint, conservative auto detection, local context envelopes.
- **M2 / M2.1 Smarter Clip Intelligence:** scene-local ranking, flexible durations, ending protection, story scoring, Best 3 diversity, replacement suggestions, quality metadata, memory-safe transcription fallback.
- **M3 Titles & Social Metadata:** grounded title generation, descriptions, hashtags, subject-hint grounding and richer export metadata.

## M3 behavior

Each candidate can now store:

- `title`
- `description`
- `hashtags: string[]`
- `social_caption` (description + tags for backward/generic publisher compatibility)
- `context.grounded_terms`
- `context.copy_version = "m3"`

M3 uses the selected clip as the factual basis and the M2 local scene envelope for topic context. For compilation sources that envelope is bounded by scene segmentation. The optional subject hint is trusted user-supplied context; the copywriter must not invent named characters/people.

Export-package `metadata.json` and per-render `.metadata.json` sidecars contain the new description and hashtag fields.

## Validation at checkpoint

- Backend: **68 tests passed**.
- Python modules compile successfully.
- All edited TSX files pass TypeScript parser/transpile syntax validation.
- Full Next production build is intentionally re-run on the user's Windows install because this workspace could not finish installing Next dependencies.

## Next milestone: M4 — Visual & Caption Intelligence

Priority items agreed with the user:

1. reduce face tracking further; stable central framing by default;
2. reset crop decisions on shot/scene changes so anime/film cuts do not inherit stale face positions;
3. add saliency-style fallback for anime/gameplay/documentary instead of face chasing;
4. detect existing/burned-in subtitles and move Clip AI captions to a safer zone or warn;
5. make caption style/density content-aware (cleaner/lower text for anime/film, denser podcast, viral for meme/comedy);
6. merge old Meme + Viral Pop presentation choices into one clearer **Viral** behavior where practical while preserving old project compatibility;
7. keep platform-safe caption zones for TikTok / Shorts / Reels;
8. target speed by doing expensive visual analysis only on chosen candidate ranges and using low-resolution proxy sampling.

Do not make Clip Relay a public dependency. Do not remove M2 dynamic clip lengths/natural ending protection while doing visual work.
