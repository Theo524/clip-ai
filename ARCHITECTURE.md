# Clip AI v23 M5 architecture

Clip AI remains a local-first public product: the Next.js UI controls a FastAPI worker that performs media analysis, English speech transcription, ranking, reframing, captions and rendering on the user's PC.

```text
Next.js web app
  ├─ upload / authorised YouTube source
  ├─ Content type + Video structure + optional subject hint
  ├─ processing profile
  ├─ progress / recovery / Projects
  ├─ Best 3 + replacement / trim / transcript correction
  └─ preview / render / export
                 ↓
FastAPI worker 23.0.0-beta.9
                 ↓
FFprobe media/audio preflight
  └─ Auto prefers a clearly labelled English audio stream
                 ↓
optional stable H.264/AAC normalization
                 ↓
English transcript checkpoint/cache (version v23.5-english-quality)
  ├─ current project transcript → reuse
  ├─ current content-keyed cache → reuse
  └─ miss → FFmpeg mono audio chunks
                 ↓
Whisper transcription
  ├─ Balanced → base.en, stronger beam
  ├─ Fast/Low-memory → tiny.en + confidence rescue to base.en
  └─ explicit subject hint → initial context + hotwords when supported
                 ↓
transcript quality check
  ├─ word confidence
  ├─ weakest sentence confidence
  ├─ low-confidence ratio
  └─ repetition/hallucination signal
                 ↓
questionable chunk only → stronger second pass → keep better result
                 ↓
scene-local narrative ranking
  ├─ setup/payoff/reaction continuation
  ├─ boundary confidence
  ├─ boundary repair cost
  └─ diverse Best 3
                 ↓
grounded title / description / max-5 useful tags
                 ↓
smart reframe + ASS captions from transcript words
  └─ intentional clean/cinematic line breaks
                 ↓
MP4 / cover / SRT / VTT / metadata / export ZIP
```

## Speech policy

Local speech transcription is intentionally English-only. There is no language selector, language-detection model, or automatic Japanese/other-language translation. If multiple audio streams exist, Clip AI automatically prefers a clearly-labelled English dub. A clearly-labelled non-English-only track is rejected with a clear message asking for an English dub/source. Unlabelled streams are allowed because many normal English files omit language metadata.

The optional subject hint is the only trusted vocabulary context for Whisper. M5 may provide that hint as hotwords if the installed faster-whisper build exposes the feature. Filenames are never used as trusted speech terms.

## Caption fidelity

Spoken captions and social copy remain separate. ASS captions are built from the actual word-timed transcript. M5 may change **where a visual line break appears**, but it does not rewrite the spoken words. Manual transcript corrections preserve existing word timings when possible.

## Anime visual contract

Anime Auto must remain:
- true-black 9:16 canvas;
- **Focus + Compact** central picture (roughly 62.5% / 3.75 of 6 vertical parts);
- Cinematic caption style;
- captions low **inside the actual anime picture**, never in the black bars;
- calm scene-aware tracking.

## Persistent state / safety

Projects live under `WORK_DIR/<project-id>`. Durable state includes project metadata, transcript, ranked clips and finished renders. The cross-project transcript cache is disposable; per-project transcripts are durable. Transcript cache identity includes the transcription strategy/version and chosen audio track. The M5 strategy bump refreshes old M4.4 transcripts only when the project is re-analysed.

## UI rule

Keep the public Create form focused on Content type, Video structure, optional Show/program/subject, and Processing profile. Do not re-add Clip length, Audio track or language selectors unless explicitly requested.
