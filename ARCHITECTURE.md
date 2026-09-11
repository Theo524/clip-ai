# Clip AI architecture — Milestone 12

## Inputs

### Your video
A normal local video upload is saved into a per-job work directory and processed directly.

### YouTube link
The worker validates the URL and uses YouTube's public oEmbed endpoint for lightweight metadata (title, channel, thumbnail). The user then supplies an authorised local source file for processing. The source URL is retained as the project identity in the analysis response and `youtube_source.json`.

This separation is deliberate: YouTube metadata and actual video-byte ingestion are different concerns. We do not make the core clip engine depend on an unofficial downloader.

## Processing pipeline

source video
→ FFmpeg audio chunks
→ faster-whisper word-level transcript
→ local/OpenAI ranking backend
→ suggested moments
→ lightweight visual sampling
→ adaptive layout plan
→ ASS caption generation
→ FFmpeg final render

## Job storage

`apps/worker/work/<job_id>/` may contain:

- `source.<ext>`
- `youtube_source.json` for YouTube projects
- `audio/` chunks
- `transcript.json`
- `clips/` generated media and reframe plans

The work directory is ignored by Git.

## YouTube endpoints

- `GET /youtube-info?url=...` — validates a YouTube URL and returns public oEmbed metadata.
- `POST /analyze-youtube-owned` — multipart request containing the YouTube URL, rights confirmation, source video file, and requested clip count.

## Future hosted import

A future hosted product can add account/cloud-source connectors without changing the analysis engine. The source-ingestion layer is intentionally separate from transcription, ranking, and rendering.
