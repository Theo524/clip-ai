# Clip AI architecture — Milestone 15

## Inputs

### Your video
A local video upload is saved into a per-project work directory and processed directly.

### YouTube link
The worker validates the URL and uses YouTube oEmbed for public title/channel/thumbnail metadata. The user supplies an authorised local source file for the actual processing. The YouTube identity stays attached to the saved project.

## Processing pipeline

source video
→ FFmpeg audio chunks
→ faster-whisper word-level transcript
→ local/OpenAI ranking backend
→ suggested moments
→ dialogue-grounded title/social-copy generation
→ lightweight visual sampling
→ adaptive layout plan
→ ASS caption generation
→ FFmpeg final render
→ ready-to-post export handoff

## Ready-to-post export

The worker stores rendered files under stable internal cache names so repeated renders can be reused. The frontend presents a cleaner export layer on top:

- title preview
- editable project-backed title/social caption
- clipboard actions
- human-readable MP4 filename
- one obvious Short download action

`GET /media/{job_id}/{filename}?download=true&name=<title>` keeps the internal media path unchanged while returning a safe browser download filename derived from `name`.

## Dialogue-based copy

`services/copywriter.py` reconstructs only the transcript text overlapping a selected clip. It produces:

- a concise clip title
- a social post caption
- Auto / Viral / Clean / Cinematic variants

The UI can regenerate or manually edit both fields. Saved edits are written into the project's clip metadata.

### Copy endpoints

- `POST /projects/{job_id}/clips/{clip_index}/generate-copy` — regenerate title/social caption from that clip's dialogue
- `PATCH /projects/{job_id}/clips/{clip_index}/copy` — save manual title/social-caption edits

## Persistent project storage

`apps/worker/work/<job_id>/` can contain:

- `project.json` — project identity, source type, clip suggestions, titles/social captions and timestamps
- `source.<ext>` — original source video
- `youtube_source.json` — YouTube source reference when relevant
- `audio/` — temporary/extracted audio chunks
- `transcript.json` — word-timestamped transcript
- `clips/` — generated Shorts, original cuts, subtitles and reframe plans

The entire `work/` directory is ignored by Git.

## Project endpoints

- `GET /projects` — saved project summaries, render counts and storage use
- `GET /projects/{job_id}` — saved clip suggestions plus existing render files
- `DELETE /projects/{job_id}` — removes the entire local project directory

## Future hosted version

The current project index is intentionally file-based for local development. A hosted version can move project metadata into PostgreSQL/Supabase and media into object storage while keeping the processing worker interface largely unchanged.
