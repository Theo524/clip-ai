# Clip AI architecture — Milestone 11

The processing pipeline remains:

1. upload/import source
2. FFmpeg audio extraction
3. local Whisper transcription with word timestamps
4. local/OpenAI moment ranking
5. visual sampling for reframe and caption-safe zones
6. FFmpeg render + ASS captions

## UX principle

The default product path is now intentionally one decision:

`pick clip → Create Short`

Auto determines the normal framing and caption style. Manual controls live behind **Customize** and advanced caption offset lives one level deeper.

## Caption renderer change

Viral/Meme previously used two simultaneously visible layers:

- persistent base phrase
- active-word overlay

When the active word moved/scaled, the unchanged word underneath could become visible and look doubled. Milestone 11 renders one complete phrase per active-word interval. The event has no word-to-word fade or movement; only the active word receives colour and a small scale transform. This removes the ghost layer while preserving word-level sync.

## Format guide

The web UI explains:

- final local output: 720×1280 (9:16)
- Fill / Focus / Backdrop / Preserve
- Focus/Backdrop window sizes: Compact / Balanced / Immersive
- Viral Pop / Cinematic / Clean / Meme
- Auto as the recommended beginner option
