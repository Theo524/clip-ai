# Clip AI v20 architecture

v20 keeps the v19.1 media pipeline and adds a thin beta-readiness layer around it.

```text
Next.js UI
  ├─ Create
  ├─ Projects
  ├─ System / preflight
  └─ first-run onboarding
        ↓
FastAPI worker 20.0.0-beta.1
  ├─ /system/preflight
  ├─ /system/cleanup
  ├─ background analysis tasks
  ├─ background render tasks
  ├─ projects/history
  └─ media serving
        ↓
Local processing
  FFmpeg / FFprobe
  → faster-whisper word timestamps
  → local/OpenAI moment ranking
  → title/post copy
  → visual sampling + stabilized speaker tracking
  → adaptive layout + caption renderer
  → atomic MP4 render + cover frame
```

## Preflight model

`GET /system/preflight` checks required dependencies without performing a video analysis. The current checks include:

- FFmpeg and FFprobe on PATH
- writable work directory
- configured transcription backend
- configured ranking backend
- OpenCV availability for smart reframing
- free disk space

The response also reports the app version, project storage use, total/free disk, current Whisper model and a local/external processing privacy summary.

Only **required** failures mark the worker not ready. Optional visual warnings can degrade gracefully to safer framing.

## Cleanup model

`POST /system/cleanup` uses the existing stale-work cleanup rules. It may remove:

- interrupted atomic `*.part.*` outputs
- extracted audio directories for projects that already have a saved transcript

It does not remove source videos, transcripts, project metadata or successful renders.

## Stabilized virtual camera retained

The v19.1 reframe stabilizer remains the active tracking strategy. Face/active-speaker observations pass through a horizontal dead zone and hysteresis layer. Small detector changes and normal head movement do not move the camera. Reframing is reserved for sustained edge drift, confident speaker changes or meaningful scene changes.

## Deployment boundary

The local worker stores project media under `WORK_DIR` and keeps task state in memory. A hosted SaaS deployment should replace those local assumptions with durable object storage, a database, a real job queue, authentication/authorization, quotas and isolated rendering workers. v20 does not pretend those deployment systems exist yet.
