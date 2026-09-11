# Clip AI v20.1 architecture

v20.1 keeps the v19.1/v20 creative pipeline and adds a reliability/cache layer around transcription plus a simpler default UI.

```text
Next.js web app
  ├─ Your video / authorised YouTube project
  ├─ Best 3 compact results
  ├─ More suggestions & editing options (collapsed)
  ├─ task progress / cancel
  ├─ Projects
  └─ System
        ↓
FastAPI worker 20.1.0-beta.1
        ↓
ffprobe audio check
        ↓
fast content fingerprint
        ├─ project transcript exists → reuse
        ├─ transcript cache hit → reuse
        └─ cache miss
             ↓
        FFmpeg 16 kHz mono audio extraction
             ↓
        long source? up-to-10-min chunks
             ↓
        faster-whisper tiny.en, VAD on
             ↓ empty chunk
        automatic retry with VAD off
             ↓
        word-level transcript
             ↓
        persistent transcript cache
             ↓
local/OpenAI moment ranking
        ↓
copy/title generation
        ↓
saved project
        ↓
smart reframe + captions + FFmpeg render
```

## Transcript cache

Cached transcripts live under:

```text
WORK_DIR/cache/transcripts/
```

The cache key uses a fast fingerprint of file size + the first/last 1 MiB plus the transcription strategy/model. It is intentionally a local-development performance cache rather than a security identity primitive.

## Long-video behavior

Sources at least 30 minutes long are split into at most 10-minute transcription chunks even if `AUDIO_CHUNK_SECONDS` is larger. The model remains loaded in memory, chunks are processed sequentially to stay safe on an 8 GB development PC, and the worker estimates remaining time after it has measured one chunk.

Parallel transcription is deliberately avoided on the current local build because multiple concurrent decodes would compete for RAM/CPU and can make an 8 GB machine less stable rather than faster.

## Empty-transcript recovery

1. Check that the source has an audio stream with ffprobe.
2. Transcribe each chunk with VAD enabled.
3. If a chunk produces zero segments, retry the same chunk with VAD disabled.
4. Only fail after both attempts produce no English speech.

## Deployment boundary

The local worker still stores project media on disk and task state in memory. A hosted release should move source/render media to object storage, projects/users to a database, jobs to a durable queue, and long-video transcription/rendering to scalable cloud workers.
