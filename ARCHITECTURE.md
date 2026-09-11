# Clip AI Architecture — Milestone 9

## Pipeline

```text
video upload
  ↓
FFmpeg audio extraction/chunking
  ↓
faster-whisper
  ├─ segment timestamps
  └─ word timestamps
  ↓
transcript.json
  ↓
clip ranking
  ↓
selected clip
  ├─ lightweight visual sampling
  │    ├─ horizontal subject reframe plan
  │    └─ coarse vertical face occupancy
  └─ word timings
       ↓
caption phrase builder
  ├─ stable phrase event
  └─ active-word overlay events
       ↓
caption-safe zone selection
       ↓
ASS caption track
       ↓
FFmpeg adaptive 720×1280 render
```

## Stable Viral / Meme captions

Milestone 8 redrew a complete highlighted phrase for every active-word interval. Even with correct word timing, that meant phrase-level animation state restarted whenever the active word changed.

Milestone 9 separates the caption into two layers:

```text
Layer 0: persistent base phrase
Layer 1: active word only
```

For a four-word phrase, the ASS track contains one Layer 0 event spanning the whole phrase plus four short Layer 1 events. Non-active words in Layer 1 are transparent but remain in the text layout. This keeps the accent word registered over the persistent phrase.

The active word uses colour/outline emphasis and a tiny vertical `move()` animation. It deliberately avoids scale-based reflow, so the phrase does not shift horizontally as different words become active.

## Phrase transitions

Phrase-level fades are still allowed, but only once at phrase entry/exit. Active-word overlay events do not use `fad()`.

## Caption-safe placement

The smart reframe pass already samples frames for faces. Milestone 9 reuses those samples to count the dominant important-face position in three coarse bands:

```text
upper
middle
lower
```

`choose_caption_zone()` combines those occupancy counts with style preferences:

- Cinematic: lower → middle → upper
- Viral / Meme: middle → lower → upper
- Clean: lower → middle → upper

A small preference penalty means captions only move away from their natural band when another band is meaningfully less occupied by faces.

This stays lightweight enough for the 8 GB development machine because it does not add another visual-analysis pass.

## In-picture coordinates

Caption zones are always resolved relative to the actual picture region.

For Focus / Backdrop, the caption Y coordinate is calculated inside the central content window, not across the full 9:16 canvas. Therefore Cinematic captions never drift into the dark/blurred margins.

Default zone ratios within the picture are approximately:

```text
upper   34%
middle  62%
lower   85%
```

## Cache versioning

Milestone 9 uses `reframe_v9_*`, `captions_v9_*`, and `short_v9_*` filenames. This intentionally prevents a Milestone 8 cached Short from hiding the new caption behaviour after an upgrade.

## Existing layout system

- Fill — full 9:16 smart crop.
- Focus — large central portrait-friendly crop on a quiet dark canvas.
- Backdrop — Focus crop with a blurred canvas.
- Preserve — already-vertical source.

All caption styles remain inside the actual picture area.
