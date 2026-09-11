# Architecture — Milestone 3

## Current flow

```text
Browser upload
  -> FastAPI /analyze-upload
  -> work/<job-id>/source.ext
  -> FFmpeg audio chunks
  -> local faster-whisper
  -> local/OpenAI ranker
  -> ranked timestamps + job_id
  -> browser result cards
  -> POST /render-clip { job_id, start, end }
  -> FFmpeg H.264/AAC cut
  -> work/<job-id>/clips/*.mp4
  -> /media/<job-id>/<file>
  -> browser player/download
```

The `job_id` is the link between analysis results and the original uploaded source. The frontend never sends an arbitrary local filesystem path to the render endpoint.

## Security boundary

- Render requests only reference generated job IDs.
- Job IDs and media filenames are validated before filesystem access.
- The renderer only looks for `source.*` inside the chosen job directory.
- Arbitrary YouTube downloading remains out of scope; real analysis is intended for content the user owns or is authorised to process.

## Why re-encode clips

Milestone 3 uses H.264 video + AAC audio rather than stream-copying. This is slower than a keyframe-only copy, but it gives frame-accurate cuts and browser-compatible output across varied source codecs.

## Next

The render stage becomes a composition stage: 9:16 framing, subtitle timing/layout, face-aware crops, and optional branding.
