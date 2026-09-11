# Clip AI v16 architecture

```text
Upload / authorised YouTube project
            ↓
FFmpeg audio extraction
            ↓
faster-whisper (segment + word timestamps + confidence)
            ↓
local/OpenAI clip ranking
            ↓
smart title + social caption
            ↓
subject-aware reframe plan
            ↓
caption phrase engine
  - punctuation + pause boundaries
  - style-specific phrase lengths
  - dangling-fragment rebalance
  - low-confidence filler filtering
  - exact word highlighting
            ↓
platform safe-zone adjustment
            ↓
FFmpeg 9:16 render
            ↓
suggested cover-frame extraction
            ↓
projects/history + ready-to-post panel
```

## Caption philosophy

Caption timing remains grounded in Whisper word timestamps. v16 does not rewrite spoken dialogue with a language model; it only chooses which reliable tokens to display together and where phrase boundaries should fall. Very low-confidence filler/noise tokens can be hidden, but substantive words are preserved.

## Platform presets

Shorts, TikTok and Reels all still export 720×1280 locally. The preset primarily changes lower-caption safe zones to reduce collisions with platform interface chrome.

## Cover frames

After rendering a Short, FFmpeg extracts a JPEG at roughly 34% into the finished clip. This is a suggested cover preview, not yet a full automatic thumbnail-ranking system.
