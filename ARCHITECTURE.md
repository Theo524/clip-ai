# Clip AI v22 M4 architecture

v21 keeps the existing creative pipeline but adds durable local task/project state and an editing/export layer around it.

```text
Next.js web app
  ├─ upload / authorised YouTube project
  ├─ processing profile
  ├─ task progress + cancel/recovery
  ├─ Best 3 + clip editor
  ├─ caption correction + cover selection
  ├─ Projects search/filter/resume
  └─ System + redacted diagnostics
             ↓
FastAPI worker 22.0.0-m4
             ↓
media preflight + disk guard
             ↓
optional media normalization
             ↓
transcript checkpoint/cache
  ├─ project transcript → reuse
  ├─ local cache → reuse
  └─ miss → FFmpeg audio chunks → faster-whisper
             ↓
ranking checkpoint/cache
             ↓
word transcript + ranked moments + copy
             ↓
atomic project.json (schema v22)
             ↓
smart reframe / active-speaker tracking / captions
             ↓
render cache + cover + SRT/VTT + metadata sidecar
             ↓
MP4 download or complete export ZIP
```

## Persistent local state

Project state lives under `WORK_DIR/<project-id>/project.json`. v21 adds a small task ledger at:

```text
WORK_DIR/_state/tasks.json
```

If the worker closes while a task is running, that task is converted to a recoverable interrupted state on the next start. Resume re-enters the normal analysis pipeline and relies on saved checkpoints rather than blindly discarding completed work.

## Project migrations

`project.json` uses schema version 22. Older local projects are migrated additively when loaded. New fields receive safe defaults; saved source/transcripts/clips/renders remain intact. Writes use a temporary file and replace pattern to reduce partial JSON corruption after a crash.

## Media normalization

FFprobe is used before transcription to inspect streams, codecs, dimensions, frame rate and rotation metadata. Media that is likely to cause inconsistent downstream behavior can be converted once to `normalized.mp4` using H.264 video and AAC audio. The original source is retained.

## Processing profiles

Profiles centralize resource choices rather than exposing implementation settings to normal users:

| Profile | Audio chunks | CPU threads | Intended use |
| --- | ---: | ---: | --- |
| Low memory | 300s | 2 | constrained/RAM-sensitive machine |
| Balanced | 600s | 4 | default local beta |
| Fast | 1200s | 6 | machine has spare CPU/RAM |

Actual render/transcription behavior still respects the existing local model/backend settings.

## Checkpoints and caches

Clip AI can reuse:
- existing project transcript;
- content-keyed transcript cache;
- saved ranked clips;
- existing rendered files/reframe data when exact inputs match.

This is especially important for long videos: a later render/edit failure should not force a completed transcription to start over.

## Generic export boundary

The complete export package and `.metadata.json` sidecar are deliberately generic. They contain finished media metadata but do not reference or require any private companion application. This keeps the public Clip AI product standalone.

## Security/support boundary

The diagnostics endpoint produces a ZIP of useful environment/project/task information while excluding API keys, transcript contents and obvious secrets. It is a support artifact, not telemetry; nothing is uploaded automatically.

## Future hosted deployment

A hosted public release should replace local disk/task state with authenticated accounts, object storage, a database and a durable queue; processing should run on isolated scalable workers. v21's project/checkpoint boundaries are designed to make that migration easier later.


## v22 context and M2 ranking

Projects persist requested/resolved content type, requested/resolved structure, optional subject hint, confidence/signals, and a local context envelope per clip. M2's local selector records scene bounds, moment types and quality warnings; the context envelope is clamped to the scene. Existing M1 projects retain their saved clips when resumed.

## v22 M4 visual pipeline

The render endpoint resolves the saved project content type before visual analysis. `plan_smart_reframe()` only scans the requested clip range on a <=480 px proxy. Anime/film gets a conservative cinematic profile, gameplay/documentary can use saliency-guided visual tracking, and podcast/talking-head clips retain speaker-aware behavior. Shot cuts clear stale tracking state and split stabilization into independent scenes.

Auto anime rendering uses `preserve`, which scales the whole source frame into the 9:16 canvas. `picture_window()` exposes the actual visible source rectangle so ASS captions stay inside the anime/film picture. Repeated lower subtitle-like samples cause Auto captions to move away from the lower band. The public `meme` style was merged into `viral`, with the old API value retained as a compatibility alias.
