# Clip AI v18.1 architecture

```text
Upload / authorised YouTube project
            ↓
FFmpeg audio extraction
            ↓
faster-whisper
(segment + word timestamps + confidence)
            ↓
local/OpenAI moment ranking
            ↓
Best 3 + editor explanations
            ↓
smart title + social caption
            ↓
visual sampling
  faces + groups
  motion + scene cuts
            ↓
lightweight speaker inference
  transcript says speech is active
  + lower-face motion > upper-face motion
  + confidence margin over other faces
            ↓
conservative speaker state
  clear same speaker → follow smoothly
  uncertain → group center
  possible switch → require 2 samples
  camera cut removes old speaker → switch safely
            ↓
Auto layout profile
  stable single face → Fill + Viral
  group/dialogue → Focus + Cinematic
  motion/gameplay → Backdrop + Meme
  portrait → Preserve + Clean
            ↓
caption phrase engine
  punctuation + pause boundaries
  word-level highlighting
  platform safe-zones
            ↓
FFmpeg 9:16 render + cover frame
            ↓
projects/history + ready-to-post panel
```

## Why this is not full speaker diarization

The local development machine has 8 GB RAM, so v18 avoids adding a large audiovisual speaker model. Instead it combines information already available in the pipeline: Whisper tells us when speech is occurring, Haar face detection gives candidate faces, and sampled lower-face motion supplies a cheap visual clue.

This is intentionally conservative. A false positive that aggressively crops to the wrong actor is worse than keeping both actors visible, so weak evidence falls back to the group center.

## Reframe plan

`ReframePlan` now stores:

- `active_speaker_samples`
- `active_speaker_switches`
- `group_fallback_samples`
- `speaker_hold_samples`

These travel with the cached reframe plan and are exposed in render metadata. Reframe cache filenames are versioned as `reframe_v18_*`, so old v17 plans are not silently reused.

## FFmpeg tracking-expression safety

Before rendering, dense reframe tracks are simplified with a time-aware curve reduction and capped to a safe number of keyframes. This avoids the FFmpeg nested-expression parser failure seen in v18 on ~45s+ active-speaker clips while retaining endpoints and important direction changes.

## Render safety

Speaker movement is still converted into a smoothed crop-center track rather than hard jump cuts. Multi-person Auto layouts continue to preserve more scene context, and the caption safe-zone system remains independent of the speaker tracker.
