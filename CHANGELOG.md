# Changelog

## 23.0.0-beta.3 · M2 Boundary Refinement

- Keeps the simplified Content type + Video structure UI from M1.1.
- Detects immediate reaction/payoff lines so anime, film and comedy clips do not cut just before the reaction.
- Uses local semantic continuity to avoid stopping while the same idea is still being completed.
- Rewards clips that include the compact setup needed for a reply/answer.
- Adds internal boundary-confidence scoring and lightly prefers the shortest complete version of a moment.
- No framing/caption changes; Anime Auto remains black canvas + Compact frame + Cinematic captions low inside the picture.

## 23.0.0-beta.2 · M1.1 Simpler Context UI

- Removes the public **Clip length** selector; Narrative Intelligence decides length automatically from setup/payoff/completeness.
- Removes the public **Audio track** selector; the worker keeps automatic/default-track handling internally.
- Keeps **Content type** and **Video structure** as the two main context choices, plus the optional show/program/subject hint.
- Removes the audio-track project badge to reduce UI clutter.
- No ranking, transcription, framing, caption, or rendering behavior is otherwise changed from v23 M1.
- Backend regression suite remains 98 tests.

## 23.0.0-beta.1 · Narrative Intelligence 2.0

- Adds narrative-completeness scoring as a first-class ranking dimension.
- Extends clips when a question, setup, pivot or immediate payoff would otherwise be cut off.
- Penalizes openings that depend on missing setup, including reply/pronoun-only starts.
- Avoids padding already-complete short moments simply because more dialogue follows.
- Allows longer anime/film/podcast/documentary candidates only when the narrative needs it.
- Keeps scene/compilation boundaries hard: context extension never crosses into the next detected scene.
- Exposes `Narrative` in the existing score breakdown and stores narrative completeness in candidate metadata.
- Ranking checkpoint version changed so saved v22 candidates are safely re-ranked once under v23 logic.
- 98 backend tests pass.

## 22.0.0-beta.1 · M6 Long-Term Beta Freeze

- Added user-selectable audio tracks for dual-audio/multilingual sources; Auto follows the source default track.
- Multi-audio sources are normalized with the selected track so Whisper and rendered Shorts use the same audio.
- Transcript-cache identity now includes audio-track selection.
- Added per-project **Free space** cleanup that preserves finished Shorts, covers, transcript, metadata and export packages while optionally deleting the original/normalized source.
- Added bounded transcript-cache cleanup (30-day age policy / ~512 MB cap) without touching per-project transcripts.
- Added lightweight analysis timing/performance metadata and Project-card duration display.
- Project schema advanced to 24 with additive migration defaults.
- Updated Windows updater to clean stale code and Next/Turbopack cache while preserving Git, venv, work/projects and settings.
- Backend regression suite: 92 tests passed.

## 22.0.0-M5 · Editing & Workflow

- Locked Anime + Cinematic + Focus captions to the lower in-frame position and moved the anchor lower (88% of the picture height).
- Added 9-second 540×960 Quick Preview renders that stay out of Saved renders.
- Added Auto / Short / Balanced / Longer story clip-length preferences with natural-boundary scoring.
- Added Render #1 only alongside Render all 3.
- Added persisted rejection reasons for replacement suggestions.
- Added private local project notes.
- Added ±100 ms caption timing nudge controls.
- Scaled Focus/Backdrop window geometry and caption font metrics proportionally for preview resolution.
- Project schema advanced to 23 with additive migration defaults.
- Backend validation: 85 tests passed.


## 22.0.0-M4.2 · Anime cinematic framing correction

- Anime Auto now uses the classic black-canvas Focus layout with the Compact central window.
- The picture occupies 800/1280 px vertically (62.5%, or 3.75/6 of the screen).
- Cinematic anime captions stay low inside the picture instead of floating in the black bars.
- Existing burned-in subtitle detection can still move captions upward when overlap would be likely.
- M4 calmer tracking, scene-cut resets, saliency fallback, and M1-M3 intelligence remain unchanged.


## 22.0.0-M4.1 · Anime framing hotfix

- Restores the familiar central cinematic framing for Anime Auto instead of forcing a tiny full-frame Preserve layout.
- Keeps M4 calmer tracking, scene-cut resets, burned-in subtitle avoidance and Cinematic caption behavior.
- Anime Auto now uses Focus + Balanced framing with Cinematic captions. Manual Preserve remains available.

## 22.0.0-M4 · Visual & Caption Intelligence

- Anime/Animation Auto now preserves the full source composition in the vertical canvas and defaults to restrained Cinematic captions.
- Widescreen Preserve is now an intentional framing choice, not a portrait-only special case; captions remain anchored inside the actual visible picture.
- Adds calmer content-aware crop tracking with fewer proxy samples, larger dead-zones and slower movement for anime/film.
- Adds shot-change detection/reset so a new scene does not inherit stale face/speaker framing from the previous shot.
- Adds lightweight saliency tracking for anime/gameplay/documentary footage as an alternative to face chasing.
- Adds conservative burned-in subtitle detection; Auto moves Clip AI captions away from repeated lower subtitle bands and reports the adjustment.
- Caption density is content-aware; anime/film Cinematic captions are smaller and use shorter phrases.
- Public Meme + Viral Pop presentation choices are merged into **Viral** while legacy `meme` project/request values remain accepted and map safely to Viral.
- Keeps platform-specific TikTok/Shorts/Reels safe zones and M1-M3 ranking/metadata behavior unchanged.
- Adds a safer Windows `UPDATE_CLIP_AI_M4.bat` that removes stale code/tests while preserving `.git`, `.venv`, local work/projects and settings, then runs tests/build/start without closing on errors.
- Backend regression suite passes 78 tests.

## 22.0.0-M3 · Titles & Social Metadata

- Replaces raw transcript-line titles with a context-aware local copy pass that favors complete, central moments and cleaner headline phrasing.
- Uses each clip plus its bounded local scene context from M2; compilation metadata never reads across a detected scene boundary.
- Adds editable descriptions and up to seven useful hashtags/tags per clip while preserving `social_caption` as a combined description + tags field for generic publishing tools.
- Uses the optional show/program/subject hint as trusted context for title grounding and tags. Clip AI does not invent character/person names that were not supplied or present in source context.
- Adds content-type and moment-type tags such as Anime, Documentary, Reveal, Podcast and Gameplay, plus a small number of grounded topic tags.
- Export packages and per-render `.metadata.json` sidecars now include `description` and `hashtags` in addition to the legacy `social_caption`.
- Results UI now exposes **Title, description & tags**, separate copy buttons, and a combined post bundle.
- Keeps M2.1 memory-safe Whisper fallback, scene-local ranking, flexible durations, Best 3 diversity and the v21 render/recovery pipeline unchanged.
- Backend regression suite passes 68 tests. Frontend TSX syntax validation passes in this workspace; run the full Next.js build on Windows after installation.

## 22.0.0-M2.1 · Memory-safe transcription patch

- Fixes the Windows/NumPy `Unable to allocate ... complex128` failure seen during faster-whisper feature extraction on memory-constrained PCs.
- Balanced now uses 5-minute audio chunks; Low memory uses 3-minute chunks; Fast uses 10-minute chunks.
- If a local Whisper chunk still hits a NumPy allocation error, Clip AI automatically retries only that chunk in progressively smaller pieces instead of failing the whole analysis.
- Keeps only one loaded local Whisper model in the in-process cache so switching processing profiles cannot leave two full models resident.
- Adds explicit regression tests for the exact 141 MiB allocation failure shape reported during M2 testing.
- M2 scene-local ranking, flexible duration, Best 3 diversity, replacement suggestions and the v21 render pipeline are otherwise unchanged.

## 22.0.0-M2 · Smarter Clip Intelligence

- New local selector favors complete thoughts over a fixed short-form duration; provides content-type soft length guides and ending checks.
- Segments transcript by pauses, topic changes and compilation cues, with optional bounded low-resolution FFmpeg keyframe cut detection for film/anime/compilations.
- Keeps candidate context within its scene, marks moment type and quality warnings, and gives Best 3 picks more scene diversity. Sampled frequent cuts add a conservative framing warning.
- Adds Replace suggestion / Restore top picks, reusing already ranked candidates. Replacements are session-only; saved M1 recommendations and edits are preserved.
- Keeps transcription, rendering, editing and exports on the established v21/M1 path. Local M2 scoring does not change the optional OpenAI ranking backend.
- Backend suite passes 58 tests; frontend TypeScript check passes. Production build needs validation on Windows because the current workspace process runner fails inside Next before compilation.

## 22.0.0-M1 · Context Foundation

- Added content type selection: Auto, Podcast/Interview, Anime/Animation, Film/TV, Documentary/Educational, Meme/Comedy, Gameplay/Commentary and Other.
- Added video structure selection: Auto, Single story/episode, Compilation/mixed clips and Conversation.
- Added optional show/program/subject hints, stored as context rather than assumed facts.
- Added conservative transcript-based Auto detection for content type and source structure.
- Added per-candidate local context envelopes so compilation clips can use nearby context in M2 instead of unrelated parts of the upload.
- Added schema-v22 project migration while keeping old v21 projects compatible.
- Added context badges to results/projects without changing the proven v21 ranking/render pipeline yet.
- Backend regression suite now passes 51 tests.


## 21.0.0-beta.1 · Long-Term Beta

- Added persistent/recoverable task history and project status.
- Added Resume for interrupted projects with checkpoint/cache reuse.
- Added media/audio preflight, optional normalization and free-disk guard.
- Added Low memory / Balanced / Fast processing profiles.
- Added safer temporary-file cleanup and schema-v21 project migration.
- Added manual clip timing edits and transcript/caption corrections.
- Added selectable cover frames.
- Added SRT/VTT exports and complete export packages.
- Added generic per-render metadata sidecars.
- Added Projects search/filter/status and resume controls.
- Added redacted diagnostic export.
- Added Windows start/check launchers.
- Expanded reliability/regression coverage to 46 backend tests.
- Preserved the dark-glass visual refresh and floating navbar polish.
