# v23 M5 — Final Quality Pass

- Keeps local speech English-only; Japanese/multilingual detection and translation remain removed.
- Adds optional faster-whisper hotword vocabulary derived only from the explicit Show/program/subject hint.
- Uses a slightly stronger Balanced English beam while preserving base.en, confidence rescue and low-memory fallback.
- Bumps the transcription strategy/cache version so M4.4 transcripts refresh once under the M5 speech path.
- Adds intentional balanced Clean/Cinematic caption line breaks without changing spoken wording.
- Improves title extraction so long dialogue is reduced to a meaningful clause before length trimming.
- Improves description shortening so copy stops at natural clause edges instead of mid-thought.
- Restores trusted subject/show casing consistently in generated metadata and keeps the no-invented-names rule.
- Filters more generic conversational verbs/adjectives from free-form hashtags.
- Makes strong immediate reactions mandatory continuation even after a spoken closure, reducing setup/payoff/reaction cuts.
- Adds `boundary_repair_cost` to internal candidate quality and penalizes warning-heavy boundaries more directly.
- Preserves all M4.4 long-video and render-memory safeguards.
- Preserves Anime Auto exactly: black 9:16 canvas, Compact central picture, Cinematic captions low inside the picture, calmer tracking.
- Regression suite: **135 passed, 0 failed**.

# v23 M4.4 — English-only speech rollback

- Removed experimental automatic language detection and Japanese/multilingual translation after real-world testing.
- Local transcription is English-only again; no multilingual Whisper models are loaded or downloaded.
- Dual-audio media still automatically prefers a clearly-labelled English dub.
- Clearly-labelled non-English-only audio now returns a clear English-dub/source message instead of misleading captions.
- Kept the stronger English transcript rescue, copy quality, long-video memory safety, and render-memory hotfixes.

# Changelog

## v23 M4.3 - Render Memory Safety Hotfix

- Releases the cached local Whisper/CTranslate2 model before Short encoding so FFmpeg/x264 has more RAM available on 8 GB Windows machines.
- Detects x264/FFmpeg allocator failures such as `malloc ... failed` and retries the same render automatically with a single-thread, ultrafast low-memory encoder configuration.
- Keeps the same 720x1280 final canvas, framing, captions, timing, metadata, and clip selection; the fallback changes encoder memory usage rather than content.
- Hardens the Windows updater with a larger Node build heap and a Webpack fallback if Turbopack cannot complete the production build.
- Regression suite: 125 tests passing.

# v23 M4.2 — Long-video memory hotfix

- Recognizes Windows/Intel MKL `mkl_malloc: failed to allocate memory` as a recoverable memory-pressure error.
- On multilingual OOM, retries the failing chunk with the lower-memory multilingual Whisper model before splitting audio further.
- Clears the cached Whisper model before lower-memory retry to release RAM sooner.
- Uses smaller speech chunks automatically for roughly 45+ minute sources, without adding another UI control.
- If language probing runs out of RAM, falls back to unknown/multilingual handling instead of incorrectly forcing English.
- Keeps M4.1 speech/copy quality behavior and all visual presets unchanged.

# Clip AI v23 M4.1

- Fixed Windows regression tests where mocked audio chunk paths intentionally do not create a real MP3 file.
- Language detection now treats probing as optional and lets the real transcription path own file/extraction errors.
- No changes to Japanese handling, caption quality, anime framing, or metadata behavior.

# Clip AI changelog

## 23.0.0-beta.5 · Speech & Copy Quality Pass

- Adds automatic spoken-language handling with no new public language selector.
- Automatically prefers a clearly labelled English audio track on dual-audio media; otherwise uses the default track and translates non-English speech when needed.
- Uses a lightweight multilingual language probe when stream metadata is inconclusive.
- Adds Japanese/other-language → English local transcription using multilingual Whisper (`small` on Balanced, `base` on Low memory).
- Balanced English transcription now uses `base.en`; Fast/Low-memory retain the fast first pass and automatically rescue uncertain chunks with the stronger model.
- Adds transcript-quality scoring using word confidence, repeated-token detection and weakest-sentence confidence.
- Runs a focused second transcription pass only when a chunk looks unreliable, then keeps whichever transcript scores better.
- Uses the explicit Show/program/subject hint as light Whisper vocabulary context to improve programme names without trusting arbitrary filenames.
- Keeps rendered captions quote-faithful to the transcript; copy generation never rewrites spoken captions.
- Manual transcript corrections now preserve original speech timing where possible instead of redistributing every corrected word evenly across the whole clip.
- Makes Anime/Film Auto social copy more restrained and scene-grounded.
- Caps hashtags at five and removes filler tags such as `#Shorts`, `#AnimeClips`, `#PodcastClips` and `#LearnSomething`.
- Removes several canned `The Truth:` / `The Secret:` title prefixes and prevents truncated titles from ending on weak connector words.
- Adds compact transcript language/quality information to saved Project cards without adding creation settings.
- Old transcripts are versioned; the first reopen/re-analysis under this quality pass creates a fresh transcript instead of silently reusing older tiny.en output.
- Preserves v23 M1-M3 ranking/boundary behavior and the established Anime Auto framing/caption layout.
- Backend regression suite: **121 passed, 0 failed**.

## 23.0.0-beta.4 · Quality Pass · Stable Candidate

- Tightens short-clip admission for story-heavy media: anime, film/TV, documentary and podcast clips can still be short, but sub-guide clips now need a very strong complete payoff instead of winning as fragments.
- Keeps genuinely short meme/comedy punchlines eligible when they are actually complete.
- Adds a composite internal `selection_quality` score that blends clip score, narrative completeness, boundary confidence and repair warnings.
- Strengthens Best 3 diversity using full candidate topic overlap, scene diversity and moment-type diversity rather than relying only on timestamp overlap/opening words.
- Skips warning-heavy/low-narrative candidates while stronger alternatives exist.
- Pins Next.js/React/TypeScript dependency versions to the validated v23 stack so future `npm install` runs do not silently pull a new major release.
- Updates public version labels from the old v22 freeze wording to the v23 Stable Candidate.
- Preserves the simple create UI: Content type + Video structure + optional subject hint; Clip length and audio handling remain automatic.
- Preserves Anime Auto exactly: black 9:16 canvas, Compact central picture, Cinematic captions locked low inside the picture, calmer tracking.
- Backend regression suite: **112 passed, 0 failed**.

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
