# Clip AI v17 architecture

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
editor score model
  Hook
  Standalone context
  Payoff
  Retention
  Clarity
            ↓
Best 3 + editor explanations
            ↓
smart title + social caption
            ↓
subject / scene sampling
  faces + groups
  motion
  scene-cut evidence
            ↓
Auto layout profile
  stable single face → Fill + Viral
  group / cut-heavy scene → Focus + Cinematic
  motion/gameplay → Backdrop + Meme
  portrait → Preserve + Clean
            ↓
caption phrase engine
  punctuation + pause boundaries
  style-specific grouping
  word-level highlighting
  platform safe-zones
            ↓
sequential batch render (optional)
            ↓
FFmpeg 9:16 render + cover frame
            ↓
projects/history + ready-to-post panel
```

## Ranking model

The local ranker still works without API credits. v17 keeps the proven boundary/hook/payoff heuristic but also produces five explicit editorial subscores. The final score blends the original heuristic with those dimensions, reducing the chance that one keyword alone dominates ranking.

The top three are presentation/UI choices, not separate copies of the clips. They point to the same candidate records shown in the full details grid below.

## Auto layout

The lightweight OpenCV sampling pass now records sampled scene-cut evidence as well as faces, multi-person frames and motion. This helps distinguish a stable talking-head shot from a wider edited/cinematic scene.

Auto frame size can choose Compact for group/cut-heavy Focus clips to preserve more horizontal context. Manual Compact/Balanced/Immersive settings always override Auto.

## Batch rendering

`Render all 3` deliberately renders sequentially in the browser by calling the existing `/render-short` endpoint for each top clip. This avoids multiplying RAM/CPU pressure on an 8 GB development machine and keeps the single-render pipeline as the source of truth.
