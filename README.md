# Clip AI v18.1

Local-first AI short-form video clipping prototype.

## v18.1 render hotfix

v18 could generate more than 100 active-speaker tracking keyframes on a longer Short. FFmpeg turns those into nested crop expressions and common builds fail around that depth. v18.1 simplifies the tracking curve before rendering, preserving important bends/speaker switches while keeping the expression below a safe parser depth.

## What v18 changes

v18 is the speaker-framing release:

- Adds **lightweight active-speaker framing** for multi-person dialogue.
- Uses Whisper speech timing plus sampled lower-face motion as a conservative proxy for who is talking.
- Requires a clear motion advantage before following a speaker; uncertain samples fall back to **group framing**.
- Requires repeated evidence before switching between two visible speakers, reducing twitchy left/right jumps.
- If a camera cut removes the old speaker, the crop can move immediately to a clear new speaker instead of framing empty space.
- Keeps Focus/group framing as the safety net for films, interviews and multi-person scenes.
- Reports speaker-switch information in the finished Short's Technical details.
- Keeps all v17 Best 3, batch rendering, scoring, adaptive captions, projects/history, covers and ready-to-post export features.

This is deliberately a lightweight local approximation rather than full production speaker diarization/lip-reading. It is designed to improve framing without adding a large ML model to an 8 GB development PC.

## Run locally

Backend:

```bat
cd apps\worker
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bat
cd apps\web
npm run dev
```

Open `http://localhost:3000`.

## How active-speaker framing works

During a Short render, Clip AI samples frames across the selected clip. When two or more meaningful faces are visible and the transcript indicates speech is happening, it compares motion in the lower part of each face with motion in the upper face. A clear lower-face motion advantage is treated as evidence that the person may be speaking.

The tracker is intentionally conservative:

1. Clear speaker evidence → bias the crop toward that face.
2. Uncertain evidence → keep the group safely framed.
3. Brief detector miss → hold the prior speaker momentarily.
4. Different visible speaker → require repeated evidence before switching.
5. Old speaker disappears after a cut → allow an immediate clear replacement.

For multi-person cinematic scenes, Auto still generally prefers **Focus + Cinematic** so the composition is not aggressively destroyed just because one person is speaking. You can manually choose Fill if you want a tighter speaker-centric podcast crop.

## Caption/transcription quality on an 8 GB PC

The safest default remains:

```env
LOCAL_WHISPER_MODEL=tiny.en
```

If you have enough free RAM, you can test:

```env
LOCAL_WHISPER_MODEL=base.en
```

`base.en` should improve transcription accuracy, but switch back to `tiny.en` if Windows reports memory-allocation errors.

## Notes

- Local Shorts render at 720×1280.
- Auto remains a recommendation system; framing, layout, caption style and size can still be overridden.
- YouTube projects use the authorised-source-file workflow rather than depending on an unofficial downloader.
