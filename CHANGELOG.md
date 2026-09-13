# Changelog

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
